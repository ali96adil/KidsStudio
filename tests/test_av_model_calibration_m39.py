"""M39 adversarial-model preflight, with REAL files and FAKE always-PASS AI.

These four visual variants use synthetic labels, NOT human-grounded
lip sync/child-safety truth. CI merely proves an unqualified all-PASS
model is rejected before any actual device authorization.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from kidsstudio.av_model_calibration import benchmark_av,CalibrationError
from kidsstudio.synchronized_av_review import AVRunner
from test_local_audio_review_m34 import executable
from kidsstudio.real_media_evidence import digest
from test_synchronized_av_m37 import SynchronizedAV37


class AVCrisisCanaries39(unittest.TestCase):
    def setUp(self):
        av=SynchronizedAV37(
            "test_actual_soundtrack_real_pcm_and_frames_bound_to_two_mock_AV_models")
        av.setUp();self.addCleanup(av.doCleanups)
        self.av=av
        # These are container-distinct but not true human-labeled negative
        # video examples. Real pilot needs genuine provenance and labels.
        cases={}
        cases["clean"]=av.mp4
        for case in ("audio_offset","wrong_narration","unsafe_visual"):
            path=av.root/(case+".mp4")
            subprocess.run([av.ffmpeg,"-hide_banner","-loglevel","error",
                "-nostdin","-y","-i",str(av.mp4),
                "-metadata","comment=synthetic_"+case,
                "-c","copy",str(path)],
                check=True,timeout=60,capture_output=True)
            cases[case]=path
        self.assertEqual(len({digest(p) for p in cases.values()}),4)
        self.cases=cases
        prepared=[]
        for case,video in cases.items():
            expected={
                "motion_sync":{"lip_sync":"PASS","voice_continuity":"PASS"},
                "visual_child_safety":{"no_unsafe_content":"PASS"}}
            if case=="audio_offset":
                expected["motion_sync"]["lip_sync"]="NEEDS_FIX"
            if case=="wrong_narration":
                expected["motion_sync"]["voice_continuity"]="NEEDS_FIX"
            if case=="unsafe_visual":
                expected["visual_child_safety"]["no_unsafe_content"]="NEEDS_FIX"
            prepared.append({"case_id":case,
                "mp4":str(video),"mp4_sha256":digest(video),
                "wav":str(av.wav),"wav_sha256":digest(av.wav),
                "script":str(av.script),"script_sha256":digest(av.script),
                "expected":expected})
        self.manifest=av.root/"m39_canaries.json"
        self.doc={"schema_version":1,"cases":prepared,
                  "qualification_claimed":False}
        self.save()

    def save(self):
        self.manifest.write_text(json.dumps(self.doc))

    def evaluate(self,execute=False,**change):
        args=dict(manifest=self.manifest,first=self.av.runners[0],
            second=self.av.runners[1],ffmpeg=self.av.ffmpeg,
            ffprobe=self.av.ffprobe,
            out_dir=self.av.root/"benchmark_outputs",execute=execute)
        args.update(change)
        return benchmark_av(**args)

    def test_readonly_checks_exact_media_without_running_models(self):
        with patch.object(self.av.runners[0],"evaluate",
                          side_effect=AssertionError("model should not execute")):
            result=self.evaluate()
        self.assertEqual(result["status"],
                         "M39_CANARY_BYTES_PINNED_NO_MODEL_EXECUTION")
        self.assertEqual(result["model_calls"],0)
        self.assertFalse(result["model_quality_qualified"])
        self.assertFalse(result["public_release_authorized"])
        self.assertFalse((self.av.root/"benchmark_outputs").exists())

    def test_fake_always_pass_model_is_rejected_on_negative_clips(self):
        result=self.evaluate(execute=True)
        self.assertEqual(result["status"],
                         "M39_UNSAFE_OR_UNQUALIFIED_AV_MODEL_VERDICTS")
        self.assertEqual(result["model_calls"],8)
        self.assertEqual(result["canary_count"],4)
        self.assertEqual(result["mismatched_criteria"],3)
        self.assertFalse(result["all_canaries_match"])
        self.assertFalse(result["model_quality_qualified"])
        self.assertFalse(result["owner_ground_truth_independently_verified"])
        self.assertFalse(result["mac_pi_hardware_qualified"])
        self.assertFalse(result["public_release_authorized"])
        self.assertFalse((self.av.root/"benchmark_outputs"/"clean"/"frames" /
            "frames_manifest.json").is_symlink())

    def test_label_memorizing_mock_passes_comparison_but_never_is_qualified(self):
        # Deliberately dishonest "AI": a trivial SHA table knows the labels.
        # Even a perfect score cannot become model certification.
        labels={entry["mp4_sha256"]:entry["expected"]
                for entry in self.doc["cases"]}
        runners=[]
        for i,role in enumerate(("motion_sync","visual_child_safety")):
            program=(
                "import argparse,hashlib,json\nfrom pathlib import Path\n"
                "p=argparse.ArgumentParser()\n"
                "for k in ('mp4','wav','script','frames-manifest','model','role','output'):\n"
                " p.add_argument('--'+k,required=True)\n"
                "a=p.parse_args()\n"
                "def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()\n"
                "labels="+repr(labels)+"\n"
                "roles={'motion_sync':('lip_sync','voice_continuity','character_motion'),"
                "'visual_child_safety':('age_appropriate','visual_consistency','no_unsafe_content')}\n"
                "checks={k:{'decision':labels[sha(a.mp4)][a.role].get(k,'PASS'),"
                "'evidence':'SYNTHETIC HASH MEMORIZATION ONLY and not actual perception: '+k}"
                " for k in roles[a.role]}\n"
                "result={'role':a.role,'mp4_sha256':sha(a.mp4),"
                "'wav_sha256':sha(a.wav),'script_sha256':sha(a.script),"
                "'frames_manifest_sha256':sha(a.frames_manifest),"
                "'model_sha256':sha(a.model),'checks':checks,"
                "'summary':'Mock learns original labels by hash; no audiovisual analysis.'}\n"
                "Path(a.output).write_text(json.dumps(result))\n"
            )
            binary=executable(self.av.root/f"m39_leaked_labels_{i}",
                              program+f"# mock {i}\n")
            original=self.av.runners[i]
            runners.append(AVRunner(binary=str(binary),
                binary_sha=digest(binary),
                model=original.model,model_sha=original.model_sha,
                provider_id="mock_hash_labels_"+str(i),
                model_id="synthetic-label-memorizer-"+str(i)))
        result=self.evaluate(execute=True,first=runners[0],second=runners[1])
        self.assertEqual(result["mismatched_criteria"],0)
        self.assertTrue(result["all_canaries_match"])
        self.assertEqual(result["status"],
                         "M39_CANARY_SIGNAL_MATCHED_UNVERIFIED_GROUND_TRUTH")
        self.assertFalse(result["model_quality_qualified"])
        self.assertFalse(result["owner_ground_truth_independently_verified"])
        self.assertFalse(result["mac_pi_hardware_qualified"])
        self.assertFalse(result["public_release_authorized"])

    def test_modified_source_or_repeated_media_prevents_any_model_call(self):
        self.doc["cases"][2]["mp4_sha256"]="b"*64
        self.save()
        with self.assertRaises(CalibrationError):
            self.evaluate(execute=True)
        self.assertFalse((self.av.root/"benchmark_outputs").exists())
        self.doc["cases"][2]["mp4_sha256"]=digest(self.cases["wrong_narration"])
        self.doc["cases"][2]["mp4"]=str(self.cases["clean"])
        self.doc["cases"][2]["mp4_sha256"]=digest(self.cases["clean"])
        self.save()
        with self.assertRaises(CalibrationError):
            self.evaluate(execute=True)

    def test_required_negative_labels_cannot_be_erased(self):
        self.doc["cases"][1]["expected"]["motion_sync"]["lip_sync"]="PASS"
        self.save()
        with self.assertRaises(CalibrationError):
            self.evaluate()
        self.assertFalse((self.av.root/"benchmark_outputs").exists())


if __name__=="__main__":
    unittest.main()
