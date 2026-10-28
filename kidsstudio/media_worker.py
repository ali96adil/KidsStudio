"""Bounded, allowlisted Mac media worker with durable *at-most-one-start* receipts.

Media task payloads contain only recipe_id. The recipe maps to owner-pinned
local artifacts; the Pi cannot supply file paths, shell commands or models.
A crashed STARTED record is quarantined and NEVER auto-executed again.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import threading
from typing import Any, Callable

from .cycle import run_character_cycle
from .workflow_audit import audit_character_workflow
from .godot_render import render_godot_project
from .episode_assembly import EpisodeAssembler, EpisodeAssemblyError
from .voice_animation_stage import StagePlan, StageError
from .resource_gate import cooperative_compute_lock
from .remote_worker import RemoteClient, RemoteWorkerError

MEDIA_KINDS = frozenset({"character_generate", "godot_render", "episode_assemble",
                         "voice_synthesize", "ltx_animate"})
HEX = re.compile(r"^[a-f0-9]{64}$")
SAFE = re.compile(r"^[a-zA-Z0-9_-]{1,80}$")
JOB = re.compile(r"^[a-f0-9]{32}$")


class MediaError(ValueError):
    """Invalid or unsafe media recipe, payload or journal transition."""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _private_path(value: str, *, directory: bool) -> Path:
    if not isinstance(value, str) or not value.startswith("/"):
        raise MediaError("Local recipe paths must be absolute.")
    path = Path(value).resolve()
    if any((part / ".git").exists() for part in (path, *path.parents)):
        raise MediaError("Media assets may not reside in a Git checkout.")
    if directory:
        if not path.is_dir():
            raise MediaError("Media project directory is missing.")
    elif not path.is_file():
        raise MediaError("Pinned recipe source file is missing.")
    return path


class MediaRecipes:
    """Private static job catalogue. NO job-controlled arbitrary source paths."""

    def __init__(self, file: str | Path):
        source = Path(file).expanduser().resolve()
        self.catalogue_sha256 = _sha(source)
        if source.stat().st_size > 60_000:
            raise MediaError("Recipe catalogue too large.")
        data = json.loads(source.read_text(encoding="utf-8"))
        if (not isinstance(data, dict) or data.get("schema_version") != 1 or
            not isinstance(data.get("recipes"), dict)):
            raise MediaError("Invalid media recipe catalogue.")
        self.recipes: dict[str, dict[str, Any]] = {}
        for recipe_id, recipe in data["recipes"].items():
            if not SAFE.fullmatch(recipe_id) or not isinstance(recipe, dict):
                raise MediaError("Invalid recipe id or body.")
            kind = recipe.get("kind")
            if kind not in MEDIA_KINDS:
                raise MediaError("Unsupported media recipe kind.")
            allowed = (
                {"kind", "output_root", "inputs", "sha256", "review_model",
                 "max_attempts", "max_repair_parts"}
                if kind == "character_generate" else
                {"kind", "output_root", "inputs", "sha256"}
            )
            if set(recipe) - allowed:
                raise MediaError("Unknown recipe fields are forbidden.")
            inputs = recipe.get("inputs")
            pins = recipe.get("sha256")
            names = (
                ("blueprint", "workflow", "profile", "reference")
                if kind == "character_generate" else
                (("project_report",) if kind == "godot_render" else
                 ("episode_recipe",) if kind == "episode_assemble" else ("stage_recipe",))
            )
            if kind == "episode_assemble" and isinstance(inputs,dict):
                provided=set(inputs)
                if provided not in ({"episode_recipe"},
                                    {"episode_recipe","scene_evidence"}):
                    raise MediaError("Only approved episode and optional scene evidence allowed.")
                names=tuple(sorted(provided))
            if (not isinstance(inputs, dict) or not isinstance(pins, dict) or
                set(inputs) != set(names) or set(pins) != set(names)):
                raise MediaError("Recipe input names/hash pins do not match.")
            root = recipe.get("output_root")
            if not isinstance(root, str) or not root.startswith("/"):
                raise MediaError("Output root must be absolute.")
            out = Path(root).resolve()
            if any((p / ".git").exists() for p in (out, *out.parents)):
                raise MediaError("Output root must not be in a Git checkout.")
            if kind == "character_generate":
                model = recipe.get("review_model")
                if not isinstance(model, str) or not 1 <= len(model) <= 80:
                    raise MediaError("Approved local review_model required.")
                attempts = recipe.get("max_attempts", 2)
                repair_parts = recipe.get("max_repair_parts", 3)
                if (type(attempts) is not int or not 1 <= attempts <= 3 or
                    type(repair_parts) is not int or not 1 <= repair_parts <= 4):
                    raise MediaError("Unsafe model attempt budget.")
            # Validate pinned sources at runtime, immediately before starting.
            for name in names:
                if not isinstance(pins[name], str) or not HEX.fullmatch(pins[name]):
                    raise MediaError("SHA256 pin is missing/invalid.")
                if not isinstance(inputs[name], str) or not inputs[name].startswith("/"):
                    raise MediaError("Recipe input path is not absolute.")
            self.recipes[recipe_id] = dict(recipe)

    def resolve(self, kind: str, recipe_id: str) -> dict[str, Any]:
        if not isinstance(recipe_id, str) or recipe_id not in self.recipes:
            raise MediaError("Unknown or unapproved local media recipe.")
        recipe = self.recipes[recipe_id]
        if recipe["kind"] != kind:
            raise MediaError("Recipe kind does not match leased job.")
        for name, filename in recipe["inputs"].items():
            path = _private_path(filename, directory=False)
            if _sha(path) != recipe["sha256"][name]:
                raise MediaError("Pinned media source changed; owner review required.")
        if kind == "episode_assemble":
            assembler=EpisodeAssembler(recipe["inputs"]["episode_recipe"])
            if len(assembler.clips)>1 and "scene_evidence" not in recipe["inputs"]:
                raise MediaError("Multi-scene montage requires frozen M14 approval evidence.")
            if "scene_evidence" in recipe["inputs"]:
                from .scene_catalogue import verify_scene_seal
                try:
                    verify_scene_seal(recipe["inputs"]["episode_recipe"],
                                      recipe["inputs"]["scene_evidence"])
                except (OSError,ValueError,TypeError,KeyError) as exc:
                    raise MediaError("Frozen M14 scene evidence no longer matches media.") from exc
        if kind == "character_generate":
            source = recipe["inputs"]
            audit_character_workflow(
                source["blueprint"], source["workflow"],
                source["profile"], source["reference"],
            )
        return recipe


class MediaJournal:
    """Mac-local SQLite fence keyed by coordinator job ID (not lease generation)."""

    def __init__(self, file: str | Path):
        self.path = Path(file).expanduser().resolve()
        if self.path.suffix != ".sqlite":
            raise MediaError("Use dedicated .sqlite journal.")
        if any((p / ".git").exists() for p in (self.path, *self.path.parents)):
            raise MediaError("Journal must reside outside Git.")
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if not self.path.exists():
            fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
        with sqlite3.connect(self.path) as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS attempts (
                  job_id TEXT PRIMARY KEY, request_sha TEXT NOT NULL,
                  kind TEXT NOT NULL, recipe_id TEXT NOT NULL,
                  state TEXT NOT NULL, result TEXT
                )
            """)
            con.execute("PRAGMA synchronous=FULL")

    def begin(self, job_id: str, digest: str, kind: str,
              recipe_id: str) -> tuple[str, dict[str, Any] | None]:
        if not JOB.fullmatch(job_id) or not HEX.fullmatch(digest):
            raise MediaError("Invalid media journal identifiers.")
        con = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        try:
            con.execute("PRAGMA busy_timeout=10000")
            con.execute("PRAGMA synchronous=FULL")
            con.execute("BEGIN IMMEDIATE")
            row = con.execute(
                "SELECT request_sha,kind,recipe_id,state,result FROM attempts "
                "WHERE job_id=?", (job_id,),
            ).fetchone()
            if row:
                if (row[0], row[1], row[2]) != (digest, kind, recipe_id):
                    raise MediaError("Job ID replayed with different inputs.")
                state, result = row[3], json.loads(row[4]) if row[4] else None
                con.execute("COMMIT")
                return state, result
            con.execute(
                "INSERT INTO attempts VALUES(?,?,?,?,?,NULL)",
                (job_id, digest, kind, recipe_id, "STARTED"),
            )
            con.execute("COMMIT")
            return "NEW", None
        except BaseException:
            if con.in_transaction:
                con.execute("ROLLBACK")
            raise
        finally:
            con.close()

    def done(self, job_id: str, result: dict[str, Any]) -> None:
        payload = json.dumps(result, sort_keys=True)
        with sqlite3.connect(self.path, timeout=10) as con:
            cur = con.execute(
                "UPDATE attempts SET state='DONE',result=? "
                "WHERE job_id=? AND state='STARTED'", (payload, job_id)
            )
            if cur.rowcount != 1:
                raise MediaError("Journal state was not STARTED.")
            con.commit()


class MediaExecutor:
    def __init__(self, recipes: MediaRecipes):
        self.recipes = recipes

    def execute(self, kind: str, recipe_id: str, job_id: str) -> dict[str, Any]:
        recipe = self.recipes.resolve(kind, recipe_id)
        dest = Path(recipe["output_root"]).resolve() / job_id
        if dest.exists():
            raise MediaError("Media output already exists; never overwrite.")
        if kind == "godot_render":
            report = Path(recipe["inputs"]["project_report"])
            with cooperative_compute_lock(Path(recipe["output_root"]).resolve().parent):
                result = render_godot_project(report.parent, dest)
            artifact = Path(result["mp4"])
            if artifact != dest / "character_preview.mp4":
                raise MediaError("Unexpected output file.")
            status = "VIDEO_RENDERED_PENDING_FINAL_VISUAL_REVIEW"
        elif kind == "episode_assemble":
            assembler = EpisodeAssembler(recipe["inputs"]["episode_recipe"])
            if assembler.output_root != Path(recipe["output_root"]).resolve():
                raise MediaError("Episode output root must match the approved media recipe.")
            report = assembler.execute(run_id=job_id)
            artifact = Path(report["final_media_path"]).resolve()
            if artifact != (dest / "episode_qa_master.mp4").resolve():
                raise MediaError("Unexpected episode output location.")
            status = "VIDEO_RENDERED_PENDING_FINAL_VISUAL_REVIEW"
        elif kind in ("voice_synthesize", "ltx_animate"):
            stage = StagePlan(recipe["inputs"]["stage_recipe"])
            if stage.kind != kind or stage.output_root != Path(recipe["output_root"]).resolve():
                raise MediaError("Pinned media stage type/output root mismatch.")
            report = stage.run(job_id)
            artifact = (dest / ("narration.wav" if kind == "voice_synthesize" else "a2v.mp4")).resolve()
            if not artifact.is_file() or report["artifact_sha256"] != _sha(artifact):
                raise MediaError("Generated stage output digest disagrees with receipt.")
            status = report["status"]
        elif kind == "character_generate":
            ins = recipe["inputs"]
            with cooperative_compute_lock(Path(recipe["output_root"]).resolve().parent):
                result = run_character_cycle(
                    ins["blueprint"], ins["workflow"], ins["profile"],
                    ins["reference"], dest,
                    vision_model=recipe["review_model"],
                    max_attempts=recipe.get("max_attempts", 2),
                    max_repair_parts=recipe.get("max_repair_parts", 3),
                )
            artifact = dest / "production_cycle.json"
            status = result["status"]
        else:
            raise MediaError("Unsupported media kind.")
        if not artifact.is_file() or not artifact.stat().st_size:
            raise MediaError("Expected local output artifact is unavailable.")
        return {
            "result_status": status,
            "artifact_sha256": _sha(artifact),
            "artifact_bytes": artifact.stat().st_size,
            "artifact_type": ("wav" if kind == "voice_synthesize" else "mp4"
                              if kind in ("godot_render","episode_assemble","ltx_animate")
                              else "rig_report"),
            "publication_approved": False,
        }


class RemoteMediaWorker:
    def __init__(self, pi: RemoteClient, recipes: MediaRecipes,
                 journal: MediaJournal, *, executor: Any | None = None):
        self.pi = pi
        self.recipes = recipes
        self.journal = journal
        self.executor = executor if executor is not None else MediaExecutor(recipes)

    def run_once(self) -> dict[str, Any]:
        job = self.pi.call("claim", {}).get("job")
        if job is None:
            return {"status": "NO_ELIGIBLE_JOB"}
        if not isinstance(job, dict) or job.get("kind") not in MEDIA_KINDS:
            raise MediaError("Media-only worker received wrong job kind.")
        job_id = job.get("job_id")
        generation = job.get("generation")
        payload = job.get("payload")
        if (not isinstance(job_id, str) or not JOB.fullmatch(job_id) or
            type(generation) is not int or generation < 1 or
            not isinstance(payload, dict) or
            set(payload) != ({"recipe_id","script_sha256","voice_sha256"} if
                             job.get("kind")=="ltx_animate" else
                             {"recipe_id","script_sha256","catalogue_sha256"}
                             if job.get("kind")=="episode_assemble" and
                               isinstance(payload,dict) and "catalogue_sha256" in payload else
                             {"recipe_id","script_sha256"} if
                             job.get("kind") in ("episode_assemble","voice_synthesize") else
                             {"recipe_id"})):
            if isinstance(job_id, str) and JOB.fullmatch(job_id) and (
                type(generation) is int and generation >= 1
            ):
                try:
                    self.pi.call("fail", {
                        "job_id": job_id, "generation": generation,
                        "error_code": "MEDIA_CONFIGURATION_REJECTED",
                    })
                except RemoteWorkerError:
                    pass
            raise MediaError("Invalid Pi media task payload.")
        kind, recipe_id = job["kind"], payload["recipe_id"]
        # Invalid local recipe is terminal, not an ambiguous GPU execution.
        try:
            local_recipe = self.recipes.resolve(kind, recipe_id)
            if kind == "episode_assemble":
                if ("scene_evidence" in local_recipe["inputs"]) != (
                    "catalogue_sha256" in payload):
                    raise MediaError("Pi and Mac disagree on mandatory multi-scene SHA pin.")
                if "catalogue_sha256" in payload:
                    if (not isinstance(payload["catalogue_sha256"],str) or
                        not HEX.fullmatch(payload["catalogue_sha256"]) or
                        payload["catalogue_sha256"] != self.recipes.catalogue_sha256):
                        raise MediaError("Frozen Mac catalogue SHA differs from owner-approved Pi job.")
                assembler = EpisodeAssembler(local_recipe["inputs"]["episode_recipe"])
                if assembler.recipe["script"]["sha256"] != payload["script_sha256"]:
                    raise MediaError("Script hash disagrees with owner-approved episode.")
            elif kind in ("voice_synthesize", "ltx_animate"):
                stage = StagePlan(local_recipe["inputs"]["stage_recipe"])
                evidence = stage.preflight()
                if stage.kind != kind or evidence["script_sha256"] != payload["script_sha256"]:
                    raise MediaError("Media stage or approved script mismatch.")
                if kind == "ltx_animate" and evidence["source_voice_sha256"] != payload["voice_sha256"]:
                    raise MediaError("LTX source WAV differs from approved voice receipt.")
        except (MediaError, EpisodeAssemblyError, StageError, OSError, ValueError):
            try:
                self.pi.call("fail", {
                    "job_id": job_id, "generation": generation,
                    "error_code": "MEDIA_CONFIGURATION_REJECTED",
                })
            except RemoteWorkerError:
                pass
            return {"status": "CONFIG_REJECTED", "job_id": job_id}
        digest = hashlib.sha256(
            json.dumps({"kind": kind, "payload": payload},
                       sort_keys=True).encode("utf-8")
        ).hexdigest()
        state, receipt = self.journal.begin(job_id, digest, kind, recipe_id)
        if state == "STARTED":
            # Deliberately no retry: ComfyUI may still be running.
            try:
                self.pi.call("fail", {
                    "job_id": job_id, "generation": generation,
                    "error_code": "MEDIA_RECONCILIATION_REQUIRED",
                })
            except RemoteWorkerError:
                pass
            return {"status": "BLOCKED_RECONCILIATION", "job_id": job_id}

        stop = threading.Event()
        errors: list[str] = []

        def heartbeat() -> None:
            while not stop.wait(45):
                try:
                    self.pi.call("heartbeat", {
                        "job_id": job_id, "generation": generation,
                    })
                except RemoteWorkerError:
                    errors.append("LEASE_OR_NETWORK_LOST")
                    return

        # Heartbeat only when an actual, potentially lengthy new render starts.
        thread = None
        if state == "NEW":
            thread = threading.Thread(target=heartbeat, daemon=True)
            thread.start()
        try:
            result = receipt if state == "DONE" else self.executor.execute(
                kind, recipe_id, job_id
            )
            if state == "NEW":
                self.journal.done(job_id, result)
        except Exception:
            stop.set()
            if thread:
                thread.join(timeout=5)
            # STARTED persists; never blindly regenerate after this failure.
            try:
                self.pi.call("fail", {
                    "job_id": job_id, "generation": generation,
                    "error_code": "MEDIA_RECONCILIATION_REQUIRED",
                })
            except RemoteWorkerError:
                pass
            return {"status": "BLOCKED_RECONCILIATION", "job_id": job_id}

        stop.set()
        if thread:
            thread.join(timeout=5)
        if errors:
            return {"status": "PENDING_ACK", "job_id": job_id}
        try:
            ack = self.pi.call("complete-media", {
                "job_id": job_id, "generation": generation, **result,
            })
            if ack.get("status") != "COMPLETED":
                raise RemoteWorkerError("Unconfirmed coordinator receipt.")
            return {"status": "COMPLETED", "job_id": job_id,
                    "result_status": result["result_status"]}
        except RemoteWorkerError:
            # Receipt is durable; only resend receipt after re-claim, no rerender.
            return {"status": "PENDING_ACK", "job_id": job_id}


def main(argv: list[str] | None = None) -> int:
    import argparse
    from .remote_worker import RemoteClient
    parser = argparse.ArgumentParser(prog="studio-media-worker")
    parser.add_argument("--coordinator", required=True)
    parser.add_argument("--ca-cert")
    parser.add_argument("--worker-id", default="mac-media-01")
    parser.add_argument("--token-env", default="KIDS_STUDIO_MEDIA_TOKEN")
    parser.add_argument("--recipes", required=True)
    parser.add_argument("--journal", required=True)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    if not args.once:
        parser.error("Explicit --once required; no autonomous daemon.")
    if not re.fullmatch(r"[A-Z][A-Z0-9_]{4,90}", args.token_env):
        parser.error("Invalid token environment variable.")
    try:
        pi = RemoteClient(
            args.coordinator, worker_id=args.worker_id,
            token=os.environ.get(args.token_env, ""), ca_file=args.ca_cert
        )
        result = RemoteMediaWorker(
            pi, MediaRecipes(args.recipes), MediaJournal(args.journal)
        ).run_once()
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result["status"] in ("COMPLETED", "NO_ELIGIBLE_JOB") else 1
    except (MediaError, RemoteWorkerError, OSError, ValueError):
        print("MEDIA_WORKER_ERROR: local policy or secure coordinator unavailable.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
