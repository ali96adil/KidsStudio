"""M11 static handoff tests: source image import and exact cross-recipe pins."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

from kidsstudio.handoff_review import inspect_handoff, HandoffError
from kidsstudio.private_asset_intake import (
    import_bunny,preview_import,verify_import,IntakeError
)


def sha(path:Path)->str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name).resolve()
        self.root=self.base/"studio";self.root.mkdir()
        self.external=self.base/"ComfyUI-Shared";self.external.mkdir()
        self.original=self.external/"Bunny_reference.png"
        self.original.write_bytes(b"\x89PNG\r\n\x1a\n"+"OWNER_BUNNY_REFERENCE".encode())
        self.assets={}
        for role in ("approved_script","voice_wrapper","ltx_wrapper",
                     "face_v06","face_v07"):
            f=self.root/(role+".py" if "wrapper" in role else role+".txt")
            f.write_text("Owner approved "+role)
            self.assets[role]=f
        self.assets["bunny_reference"]=self.original
        self.wav=self.root/"approved_voice.wav";self.wav.write_bytes(b"approved voice" * 16)
        self.python=Path(sys.executable).resolve()
        self.ffmpeg=self.root/"ffmpeg"
        self.ffprobe=self.root/"ffprobe"
        for tool in (self.ffmpeg,self.ffprobe):
            tool.write_text("#!/bin/sh\nexit 0\n")
            tool.chmod(0o700)
        self.engine={}
        for kind,name in (("voice_synthesize","chatterbox_multilingual_mlx"),
                          ("ltx_animate","ltx_2_3_mlx")):
            checkpoint=self.root/(kind+"_weights.bin")
            checkpoint.write_bytes(b"synthetic weights for "+kind.encode())
            m=self.root/(kind+"_engine.json")
            m.write_text(json.dumps({
                "schema_version":1,"kind":kind,"engine":name,
                "platform":"Darwin","arch":"arm64","minimum_memory_gib":32,
                "network_required":False,
                "checkpoints":[{"role":"model","path":str(checkpoint),
                                "sha256":sha(checkpoint)}]
            }))
            self.engine[kind]=m
        self.contract_file=self.root/"mac_contract.json"
        self.contract={
            "schema_version":1,
            "private_roots":[str(self.root),str(self.external)],
            "assets":[{"role":role,"path":str(f),"sha256":sha(f)}
                      for role,f in self.assets.items()],
            "tools":[{"role":role,
                      "path":str(self.ffmpeg if role=="ffmpeg" else
                                 self.ffprobe if role=="ffprobe" else self.python),
                      "sha256":sha(self.ffmpeg if role=="ffmpeg" else
                                   self.ffprobe if role=="ffprobe" else self.python)}
                     for role in ("voice_python","ltx_python","ffprobe","ffmpeg")],
            "engine_manifests":[{"kind":k,"path":str(f),"sha256":sha(f)}
                                for k,f in self.engine.items()],
            "minimum_free_gib":20
        }
        self.voice_file=self.root/"voice_stage.json"
        self.ltx_file=self.root/"ltx_stage.json"
        self.voice_recipe=self._recipe("voice_synthesize",self.assets["approved_script"])
        self._write(self.voice_file,self.voice_recipe)
        self._write(self.contract_file,self.contract)

    def _write(self,file,obj):
        file.write_text(json.dumps(obj,ensure_ascii=False))

    def _recipe(self,kind,reference):
        approved=self.assets["approved_script"]
        runner=self.assets["voice_wrapper" if kind=="voice_synthesize" else "ltx_wrapper"]
        inputs=(
            {"script":{"path":str(approved),"sha256":sha(approved)}}
            if kind=="voice_synthesize" else
            {"voice_wav":{"path":str(self.wav),"sha256":sha(self.wav)},
             "reference_image":{"path":str(reference),"sha256":sha(reference)}}
        )
        argv=(
          ["--script","{script}","--engine","{engine_manifest}","--output","{output}"]
          if kind=="voice_synthesize" else
          ["--script","{script}","--audio","{voice_wav}","--reference",
           "{reference_image}","--engine","{engine_manifest}","--output","{output}"]
        )
        manifest=self.engine[kind]
        return {
          "schema_version":1,"kind":kind,"private_root":str(self.root),
          "output_root":str(self.root/"output"),
          "script":{"path":str(approved),"sha256":sha(approved)},
          "inputs":inputs,
          "runner":{"python":str(self.python),"python_sha256":sha(self.python),
                    "entrypoint":str(runner),"entrypoint_sha256":sha(runner),
                    "args":argv},
          "engine_manifest":{"path":str(manifest),"sha256":sha(manifest)},
          "voice_rights":"INTERNAL_TEST_ONLY",
          "limits":{"timeout_seconds":1800,"max_output_bytes":1_000_000},
          "ffprobe":str(self.ffprobe)
        }

    def check(self,ltx=False):
        return inspect_handoff(
            self.contract_file,self.voice_file,
            ltx_recipe=self.ltx_file if ltx else None,
            system="Darwin",arch="arm64",
            memory_bytes=48*1024**3,free_bytes=110*1024**3)

    def import_reference(self):
        return import_bunny(self.original,
              approved_source_root=self.external,private_root=self.root,
              asset_id="bunny_front_v01",original_sha256=sha(self.original))

    def test_voice_handoff_without_ltx_file_has_honest_pending_status(self):
        report=self.check()
        self.assertEqual(report["status"],"VOICE_READY_LTX_RECIPE_PENDING_APPROVED_WAV")
        self.assertIsNone(report["ltx"])
        self.assertFalse(report["models_executed"])
        self.assertFalse(report["actual_wrapper_api_tested"])
        self.assertFalse((self.root/"output").exists())
        self.assertNotIn(str(self.base),json.dumps(report))

    def test_import_is_non_destructive_and_not_implicit(self):
        before=self.original.read_bytes()
        preview=preview_import(self.original,
              approved_source_root=self.external,private_root=self.root,
              asset_id="bunny_front_v01",original_sha256=sha(self.original))
        self.assertFalse(preview["import_performed"])
        self.assertFalse((self.root/"assets").exists())
        self.import_reference()
        result=verify_import(self.root,"bunny_front_v01",sha(self.original))
        self.assertEqual(result["status"],"PRIVATE_REFERENCE_COPY_VERIFIED")
        self.assertEqual(self.original.read_bytes(),before)
        with self.assertRaises(IntakeError):
            self.import_reference()

    def test_full_static_handoff_requires_versioned_import(self):
        self.import_reference()
        reference=self.root/"assets"/"imports"/"bunny_front_v01"/"bunny_reference.png"
        self.ltx_recipe=self._recipe("ltx_animate",reference)
        self._write(self.ltx_file,self.ltx_recipe)
        report=self.check(ltx=True)
        self.assertEqual(report["status"],"STAGE_MANIFESTS_MATCH_NOT_RUN")
        self.assertEqual(report["ltx"]["voice_sha256"],sha(self.wav))
        self.assertFalse(report["youtube_uploaded"])
        self.assertFalse((self.root/"output").exists())

    def test_unverified_copy_blocked(self):
        bogus=self.root/"bunny_copy.png"
        bogus.write_bytes(self.original.read_bytes())
        self._write(self.ltx_file,self._recipe("ltx_animate",bogus))
        with self.assertRaises(HandoffError):
            self.check(ltx=True)

    def test_wrong_wrapper_in_ltx_stage_rejected(self):
        self.import_reference()
        reference=self.root/"assets"/"imports"/"bunny_front_v01"/"bunny_reference.png"
        plan=self._recipe("ltx_animate",reference)
        plan["runner"]["entrypoint"]=str(self.assets["voice_wrapper"])
        plan["runner"]["entrypoint_sha256"]=sha(self.assets["voice_wrapper"])
        self._write(self.ltx_file,plan)
        with self.assertRaises(HandoffError):
            self.check(ltx=True)

    def test_script_drift_in_ltx_blocked(self):
        self.import_reference()
        reference=self.root/"assets"/"imports"/"bunny_front_v01"/"bunny_reference.png"
        other=self.root/"not_owner_script.txt";other.write_text("incorrect script")
        plan=self._recipe("ltx_animate",reference)
        plan["script"]={"path":str(other),"sha256":sha(other)}
        self._write(self.ltx_file,plan)
        with self.assertRaises(HandoffError):
            self.check(ltx=True)

    def test_missing_import_or_tampered_import_fails(self):
        self.import_reference()
        reference=self.root/"assets"/"imports"/"bunny_front_v01"/"bunny_reference.png"
        plan=self._recipe("ltx_animate",reference)
        self._write(self.ltx_file,plan)
        reference.write_bytes(b"tampered")
        with self.assertRaises(Exception):
            self.check(ltx=True)


if __name__=="__main__":
    unittest.main()
