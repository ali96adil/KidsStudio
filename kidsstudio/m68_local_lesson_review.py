"""Conservative real local Ollama script/lesson reviewer for M68.

Two independent local model endpoints must inspect the exact pinned script
and lesson content. This is advisory model evidence, not objective factual
verification, copyright clearance, or publication authorization.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib import request, error

from .local_vision_review import _endpoint, MODEL, _NoRedirect
from .m68_lesson_evidence import audit_lesson

AXES = ("pedagogy", "source_consistency")


class LessonModelError(ValueError):
    pass


class OllamaLesson:
    def __init__(self, endpoint, model, *, opener=None):
        self.endpoint = _endpoint(endpoint)
        if not isinstance(model, str) or not MODEL.fullmatch(model):
            raise LessonModelError("explicit local lesson model required")
        self.model = model
        self.opener = opener if opener is not None else request.build_opener(
            request.ProxyHandler({}), _NoRedirect())

    def run(self, *, script, lesson):
        if (not isinstance(script, str) or not isinstance(lesson, dict)
                or not 1 <= len(script) <= 8000):
            raise LessonModelError("bounded script and lesson required")
        prompt = (
            "Evaluate a children's educational SCRIPT against the declared lesson "
            "plan. You have NOT observed the actual video or audio. "
            "Do not assert video/script fidelity, copyright ownership, or "
            "factual certainty without evidence. Return only JSON with exactly "
            "keys checks and summary. checks must contain exactly pedagogy "
            "and source_consistency. Each is an object with exactly decision "
            "(PASS, UNSURE, NEEDS_FIX) and evidence (25-800 chars). "
            "source_consistency means SCRIPT versus LESSON PLAN ONLY, not video. "
            "Use UNSURE when uncertain; never authorize publishing."
        )
        payload = {"model": self.model, "stream": False, "format": "json",
                   "options": {"temperature": 0, "num_predict": 1400},
                   "messages": [
                       {"role": "system", "content": prompt},
                       {"role": "user", "content": "Script:\n" + script +
                        "\nLesson plan:\n" + json.dumps(lesson, ensure_ascii=False)}
                   ]}
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if len(body) > 60000:
            raise LessonModelError("model request exceeds size budget")
        req = request.Request(self.endpoint, data=body, method="POST",
                              headers={"Content-Type": "application/json"})
        try:
            with self.opener.open(req, timeout=180) as response:
                raw = response.read(100001)
        except (OSError, TimeoutError, error.URLError, error.HTTPError) as exc:
            raise LessonModelError("local lesson model unavailable") from exc
        if len(raw) > 100000:
            raise LessonModelError("model response too large")
        try:
            response = json.loads(raw)
            if response.get("done") is not True:
                raise LessonModelError("model did not finish")
            answer = json.loads(response["message"]["content"])
        except (ValueError, KeyError, TypeError) as exc:
            raise LessonModelError("malformed model response") from exc
        if (not isinstance(answer, dict) or set(answer) != {"checks", "summary"}
                or not isinstance(answer["checks"], dict)
                or set(answer["checks"]) != set(AXES)
                or not isinstance(answer["summary"], str)
                or not 25 <= len(answer["summary"].strip()) <= 1500):
            raise LessonModelError("model evidence incomplete")
        for row in answer["checks"].values():
            if (not isinstance(row, dict)
                    or set(row) != {"decision", "evidence"}
                    or row["decision"] not in ("PASS", "UNSURE", "NEEDS_FIX")
                    or not isinstance(row["evidence"], str)
                    or not 25 <= len(row["evidence"].strip()) <= 800):
                raise LessonModelError("invalid educational evidence")
        return answer, hashlib.sha256(raw).hexdigest()


def review_lesson(handoff, *, script_path, lesson_path, first, second):
    if (first.endpoint == second.endpoint or first.model == second.model):
        raise LessonModelError("distinct local model endpoints and model ids required")
    evidence = audit_lesson(handoff, script_path=script_path, lesson_path=lesson_path)
    if evidence["reasons"]:
        raise LessonModelError("lesson source evidence invalid")
    script = Path(script_path).read_text(encoding="utf-8")
    lesson = json.loads(Path(lesson_path).read_text(encoding="utf-8"))
    results = [runner.run(script=script, lesson=lesson) for runner in (first, second)]
    checks = {
        axis: all(answer["checks"][axis]["decision"] == "PASS"
                  for answer, _ in results)
        for axis in AXES
    }
    return {
        "status": "LESSON_MODEL_EVIDENCE_RECORDED_NOT_INDEPENDENTLY_ATTESTED",
        "short_id": handoff["short_id"],
        "source_episode_id": handoff["source_episode_id"],
        "video_sha256": handoff["sha256"],
        "script_sha256": evidence["script_sha256"],
        "model_response_sha256": [sha for _, sha in results],
        "checks": checks,
        "model_claims_independently_attested": False,
        "video_script_fidelity_verified": False,
        "youtube_upload_authorized": False,
        "public_release_authorized": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handoff", type=Path, required=True)
    parser.add_argument("--script", type=Path, required=True)
    parser.add_argument("--lesson-plan", type=Path, required=True)
    parser.add_argument("--first-endpoint", required=True)
    parser.add_argument("--first-model", required=True)
    parser.add_argument("--second-endpoint", required=True)
    parser.add_argument("--second-model", required=True)
    args = parser.parse_args(argv)
    handoff = json.loads(args.handoff.read_text(encoding="utf-8"))
    result = review_lesson(
        handoff, script_path=args.script, lesson_path=args.lesson_plan,
        first=OllamaLesson(args.first_endpoint, args.first_model),
        second=OllamaLesson(args.second_endpoint, args.second_model))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
