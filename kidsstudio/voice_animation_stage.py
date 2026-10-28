"""Pinned, owner-opt-in local Mac voice and A2V media execution.

The worker executes ONLY a local, SHA256-pinned Python entry script via its
SHA256-pinned interpreter and a fixed, pre-approved argument vector. No shell,
download, web API, provider fallback, model auto-install or public release.
Actual Chatterbox / LTX wrappers MUST implement the explicitly documented
contract and pass owner Mac qualification; CI uses fake executors.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
from typing import Any, Callable

from .episode_assembly import (
    EpisodeAssemblyError, _ensure_private, _other_file, _required_file,
    digest, probe_video
)
from .episode_sources import probe_voice

HEX = re.compile(r"^[a-f0-9]{64}$")
JOB = re.compile(r"^[a-f0-9]{32}$")
KINDS = frozenset({"voice_synthesize", "ltx_animate"})
LIMIT_BYTES = 60_000
ARGS = re.compile(r"^[A-Za-z0-9_./:=+,-]{1,180}$")
PLACEHOLDERS = frozenset({
    "{script}", "{voice_wav}", "{reference_image}", "{engine_manifest}",
    "{output}", "{recipe}"
})


class StageError(ValueError):
    """Unapproved model interface, mismatched source or dangerous execution."""


class StagePlan:
    """Validate local approved job, with exact tool + input SHA before actuation."""

    def __init__(
        self, file: str | Path, *,
        execute: Callable[[list[str], int, dict[str, str]], None] | None = None,
        voice_probe: Callable[[Path, str], dict[str, Any]] = probe_voice,
        video_probe: Callable[[Path, str], dict[str, Any]] = probe_video,
    ):
        self.path = Path(file).expanduser().resolve()
        if not self.path.is_file() or not 0 < self.path.stat().st_size <= LIMIT_BYTES:
            raise StageError("Pinned private stage recipe missing or oversized.")
        _ensure_private(self.path.parent)
        data = json.loads(self.path.read_text(encoding="utf-8"))
        required = {"schema_version", "kind", "private_root", "output_root",
                    "script", "inputs", "runner", "engine_manifest",
                    "voice_rights", "limits", "ffprobe"}
        if not isinstance(data, dict) or set(data) != required:
            raise StageError("Unknown or missing stage recipe keys.")
        if data["schema_version"] != 1 or data["kind"] not in KINDS:
            raise StageError("Unsupported stage type.")
        if data["voice_rights"] not in ("INTERNAL_TEST_ONLY", "COMMERCIAL_LICENSE_VERIFIED"):
            raise StageError("Stage needs declared voice rights.")
        self.kind = data["kind"]
        self.root = _ensure_private(Path(data["private_root"]))
        self.output_root = _ensure_private(Path(data["output_root"]))
        if not self.root.is_dir() or not self.output_root.is_relative_to(self.root):
            raise StageError("Stage outputs must remain below existing private root.")
        if set(data["script"]) != {"path", "sha256"}:
            raise StageError("Pin one approved script file.")
        if not isinstance(data["script"]["sha256"], str) or not HEX.fullmatch(data["script"]["sha256"]):
            raise StageError("Approved script digest required.")
        self.script = _required_file(data["script"]["path"], data["script"]["sha256"], self.root)
        if not isinstance(data["inputs"], dict):
            raise StageError("Stage inputs must be a mapping.")
        expected = {"script"} if self.kind == "voice_synthesize" else {"voice_wav", "reference_image"}
        if set(data["inputs"]) != expected:
            raise StageError("Stage input set does not match approved capability.")
        self.inputs: dict[str, Path] = {}
        for name, pin in data["inputs"].items():
            if not isinstance(pin, dict) or set(pin) != {"path", "sha256"}:
                raise StageError("Each input needs exact path and digest.")
            self.inputs[name] = _required_file(pin["path"], pin["sha256"], self.root)
        if self.kind == "voice_synthesize" and self.inputs["script"] != self.script:
            raise StageError("Voice source and approved episode script must match.")
        manifest = data["engine_manifest"]
        if not isinstance(manifest, dict) or set(manifest) != {"path", "sha256"}:
            raise StageError("Engine metadata manifest required.")
        self.engine_manifest = _required_file(manifest["path"], manifest["sha256"], self.root)
        runner = data["runner"]
        if not isinstance(runner, dict) or set(runner) != {
                "python", "python_sha256", "entrypoint", "entrypoint_sha256", "args"}:
            raise StageError("Runner requires approved binary, script and fixed args.")
        python = _other_file(runner["python"])
        entry = _required_file(runner["entrypoint"], runner["entrypoint_sha256"], self.root)
        if not HEX.fullmatch(runner["python_sha256"]) or digest(python) != runner["python_sha256"]:
            raise StageError("Python runtime changed since owner approved recipe.")
        argv = runner["args"]
        if not isinstance(argv, list) or not 1 <= len(argv) <= 32:
            raise StageError("Expected bounded fixed runner arguments.")
        if any(not isinstance(arg, str) or (
                arg not in PLACEHOLDERS and not ARGS.fullmatch(arg))
               for arg in argv):
            raise StageError("Runner args may contain only fixed safe tokens.")
        if argv.count("{output}") != 1 or argv.count("{script}") != 1:
            raise StageError("Runner must receive approved script and unique output.")
        if self.kind == "ltx_animate" and (
                argv.count("{voice_wav}") != 1 or
                argv.count("{reference_image}") != 1):
            raise StageError("A2V requires pinned voice WAV and character image.")
        if "{engine_manifest}" not in argv:
            raise StageError("Runner must be bound to a reviewed engine manifest.")
        if argv.count("{recipe}") > 1:
            raise StageError("Runner may only reference stage plan once.")
        if self.kind == "voice_synthesize" and any(arg in
                ("{voice_wav}", "{reference_image}") for arg in argv):
            raise StageError("Voice runner cannot accept A2V input fields.")
        self.python = python
        self.entrypoint = entry
        self.argv = argv
        self.ffprobe = _other_file(data["ffprobe"])
        limits = data["limits"]
        if not isinstance(limits, dict) or set(limits) != {"timeout_seconds", "max_output_bytes"}:
            raise StageError("Stage timeout and byte limit required.")
        timeout, maximum = limits["timeout_seconds"], limits["max_output_bytes"]
        if (type(timeout) is not int or not 30 <= timeout <= 3600 or
                type(maximum) is not int or not 100 <= maximum <= 2_000_000_000):
            raise StageError("Resource limits outside approved bounds.")
        self.timeout = timeout
        self.max_output_bytes = maximum
        self.execute_hook = execute if execute is not None else self._execute_subprocess
        self._uses_real_runner = execute is None
        self.voice_probe = voice_probe
        self.video_probe = video_probe
        self.data = data
        self.recipe_hash = digest(self.path)

    @staticmethod
    def _execute_subprocess(argv: list[str], timeout: int, env: dict[str, str]) -> None:
        """No shell, explicitly bounded time; subprocess outputs never logged."""
        try:
            child = subprocess.run(
                argv, check=False, stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                cwd="/", env=env, timeout=timeout,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise StageError("Approved local model worker failed or timed out.") from exc
        if child.returncode != 0:
            raise StageError("Approved local model worker returned failure.")

    def preflight(self) -> dict[str, Any]:
        if digest(self.path) != self.recipe_hash:
            raise StageError("Stage recipe mutated after loading.")
        if digest(self.python) != self.data["runner"]["python_sha256"]:
            raise StageError("Runner binary changed before execution.")
        _required_file(self.data["runner"]["entrypoint"],
                       self.data["runner"]["entrypoint_sha256"], self.root)
        _required_file(self.data["script"]["path"],
                       self.data["script"]["sha256"], self.root)
        _required_file(self.data["engine_manifest"]["path"],
                       self.data["engine_manifest"]["sha256"], self.root)
        for pin in self.data["inputs"].values():
            _required_file(pin["path"], pin["sha256"], self.root)
        # This validates only a pinned manifest FILE, not the full model
        # weights it may describe. Live deployment must audit those weights.
        return {
            "stage": self.kind,
            "status": "LOCAL_ENGINE_CONFIG_READY_NOT_RUN",
            "script_sha256": self.data["script"]["sha256"],
            "source_voice_sha256": (
                self.data["inputs"]["voice_wav"]["sha256"]
                if self.kind == "ltx_animate" else None
            ),
            "inference_performed": False,
            "publication_approved": False,
            "model_weights_verified": False,
            "voice_rights": self.data["voice_rights"],
        }

    def run(self, job_id: str) -> dict[str, Any]:
        if not isinstance(job_id, str) or not JOB.fullmatch(job_id):
            raise StageError("One coordinator-assigned 32-char job id required.")
        evidence = self.preflight()
        if self._uses_real_runner:
            # M8 hard gate: refuse actual local model execution until every
            # Apple Silicon checkpoint SHA and physical RAM are verified.
            from .engine_qualification import qualify_engine
            qualified = qualify_engine(self.engine_manifest,expected_kind=self.kind,
                                       private_root=self.root)
            evidence["model_weights_verified"] = bool(qualified["checkpoints"])
        self.output_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        lockfile = self.output_root / ".single_gpu_worker.lock"
        # Lock is local-only; it cannot protect unrelated Mac processes.
        lockfd = os.open(str(lockfile), os.O_WRONLY | os.O_CREAT, 0o600)
        try:
            try:
                fcntl.flock(lockfd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise StageError("Another approved local GPU stage is running.") from exc
            run_dir = self.output_root / job_id
            if run_dir.exists():
                raise StageError("Existing run detected. Manual reconciliation required.")
            run_dir.mkdir(mode=0o700)
            artifact = run_dir / ("narration.wav" if self.kind == "voice_synthesize"
                                  else "a2v.mp4")
            placeholders = {
                "{script}": str(self.script),
                "{engine_manifest}": str(self.engine_manifest),
                "{output}": str(artifact),
                "{recipe}": str(self.path),
            }
            for name, file in self.inputs.items():
                placeholders["{" + name + "}"] = str(file)
            actual = [placeholders.get(token, token) for token in self.argv]
            # Last-resort no-shell boundary. Approved entrypoint is a local
            # trusted script, so this does not constitute a network sandbox.
            cmd = [str(self.python), str(self.entrypoint), *actual]
            env = {"PATH": "/usr/bin:/bin", "HOME": str(self.root),
                   "PYTHONDONTWRITEBYTECODE": "1",
                   "KIDS_STUDIO_OFFLINE": "1"}
            status_file = run_dir / "stage_receipt.json"
            receipt = {
                "schema_version": 1, "job_id": job_id,
                "stage": self.kind, "status": "STARTED",
                "script_sha256": evidence["script_sha256"],
                "source_voice_sha256": evidence["source_voice_sha256"],
                "recipe_sha256": self.recipe_hash,
                "publication_approved": False,
                "started_at": time.time(),
            }
            status_file.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
            try:
                self.execute_hook(cmd, self.timeout, env)
                if not artifact.is_file() or artifact.is_symlink():
                    raise StageError("Expected isolated output file missing or symlinked.")
                size = artifact.stat().st_size
                if not 100 <= size <= self.max_output_bytes:
                    raise StageError("Generated media outside bounded size.")
                info = (self.voice_probe(artifact, str(self.ffprobe))
                        if self.kind == "voice_synthesize"
                        else self.video_probe(artifact, str(self.ffprobe)))
                if not 0.2 <= info["duration"] <= 180.0:
                    raise StageError("Generated media duration rejected.")
                if self.kind == "ltx_animate" and (
                        info["width"] <= 0 or info["height"] <= 0 or
                        info["audio_streams"] != 1):
                    raise StageError("A2V lacks expected audio/video.")
                receipt.update({
                    "status": "VOICE_RENDERED_PENDING_QA" if self.kind == "voice_synthesize"
                              else "A2V_RENDERED_PENDING_QA",
                    "artifact_sha256": digest(artifact),
                    "artifact_bytes": size,
                    "artifact_type": "wav" if self.kind == "voice_synthesize" else "mp4",
                    "duration_seconds": info["duration"],
                    "finished_at": time.time(),
                })
            except BaseException:
                receipt["status"] = "FAILED_REQUIRES_MANUAL_RECONCILIATION"
                status_file.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
                raise
            status_file.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
            return receipt
        finally:
            fcntl.flock(lockfd, fcntl.LOCK_UN)
            os.close(lockfd)
