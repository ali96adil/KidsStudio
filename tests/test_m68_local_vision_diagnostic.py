"""M68 vision diagnostic must not certify audio or copyright."""
import unittest
from unittest.mock import patch
from kidsstudio.m68_local_vision_diagnostic import UNOBSERVABLE, VISUAL_AXES


class VisionDiagnosticTests(unittest.TestCase):
    def test_silent_frames_never_approve_audio_or_rights(self):
        self.assertEqual(set(UNOBSERVABLE), {"audio", "copyright", "pedagogy", "source_consistency"})
        self.assertTrue(all(len(message) >= 12 for message in UNOBSERVABLE.values()))
        self.assertFalse(set(UNOBSERVABLE) & VISUAL_AXES)

    def test_all_six_review_axes_are_accounted_for(self):
        from kidsstudio.m68_short_content_review import CHECKS
        self.assertEqual(set(CHECKS), set(UNOBSERVABLE) | VISUAL_AXES)

    def test_only_directly_observed_visual_axes_can_pass(self):
        self.assertEqual(VISUAL_AXES, {"visual", "age_appropriate"})
        self.assertEqual(len(UNOBSERVABLE), 4)

    def test_real_model_call_is_deduplicated_and_response_is_pinned(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        from kidsstudio.m68_local_vision_diagnostic import run_vision_diagnostic
        from kidsstudio.m68_short_content_review import CHECKS
        from kidsstudio.m67_master_handoff import verify_inventory
        import json
        with TemporaryDirectory() as folder:
            root = Path(folder)
            script = root / "script.txt"
            script.write_text("Teach children colors safely.", encoding="utf-8")
            media = root / "short.mp4"
            media.write_bytes(b"fake-media")
            handoff = {"short_id": "short-1", "source_episode_id": "ep-1",
                       "sha256": "a" * 64}
            answers = {"checks": {
                key: {"decision": "PASS", "evidence": "Clearly safe visuals across frames."}
                for key in ("age_appropriate", "visual_consistency", "no_unsafe_content")}}
            from contextlib import ExitStack
            with ExitStack() as stack:
                stack.enter_context(patch("kidsstudio.m68_local_vision_diagnostic.verify_inventory",
                                          return_value={"sha256": "a" * 64}))
                stack.enter_context(patch("kidsstudio.m68_local_vision_diagnostic.digest",
                                          return_value="a" * 64))
                capture = stack.enter_context(patch(
                    "kidsstudio.m68_local_vision_diagnostic.capture_frames"))
                model = stack.enter_context(patch(
                    "kidsstudio.m68_local_vision_diagnostic.OllamaVision"))
                adapter = stack.enter_context(patch(
                    "kidsstudio.m68_local_vision_diagnostic.run_ai_review"))
                frame = root / "frame.png"
                frame.write_bytes(b"png-bytes")
                manifest = root / "manifest.json"
                manifest.write_text(json.dumps({"frames": [{"file": str(frame)}]}))
                capture.return_value = {"frames_manifest_file": str(manifest)}
                model.return_value.run.return_value = (answers, "b" * 64)
                def evaluate(root_arg, handoff_arg, *, infer, reviewer_id):
                    checks = {axis: infer(axis=axis, root=root_arg,
                                          handoff=handoff_arg)["passed"] for axis in CHECKS}
                    return {"decision": "REJECT", "checks": checks}
                adapter.side_effect = evaluate
                receipt = run_vision_diagnostic(root, handoff, mp4=media,
                    script=script, ffmpeg="ffmpeg", ffprobe="ffprobe",
                    endpoint="http://127.0.0.1:11434/api/chat", model="vision-model")
                self.assertEqual(model.return_value.run.call_count, 1)
                self.assertEqual(receipt["local_model_response_sha256"], "b" * 64)
                self.assertEqual(receipt["independent_reviewers"], 1)
                self.assertFalse(receipt["checks"]["copyright"])
