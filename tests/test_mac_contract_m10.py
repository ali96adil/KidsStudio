"""M10 offline Mac contract tests: no Mac commands/models are executed."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

from kidsstudio.mac_contract import check_mac_contract,MacIntakeError
from kidsstudio.engine_qualification import EngineQualificationError


def sha(path: Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as inp:
        for chunk in iter(lambda:inp.read(512*1024),b""):
            h.update(chunk)
    return h.hexdigest()


class MacContractTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()
        self.other=self.root/"comfy_private"
        self.other.mkdir()
        self.primary=self.root/"studio"
        self.primary.mkdir()
        self.assets={}
        for role in ("approved_script","bunny_reference","voice_wrapper",
                     "ltx_wrapper","face_v06","face_v07"):
            folder=self.other if role=="bunny_reference" else self.primary
            file=folder/(role+".dat")
            file.write_bytes(("synthetic:"+role).encode())
            self.assets[role]=file
        self.interpreter=Path(sys.executable).resolve()
        self.mock_ffmpeg=self.primary/"ffmpeg"
        self.mock_ffprobe=self.primary/"ffprobe"
        for tool in (self.mock_ffmpeg,self.mock_ffprobe):
            tool.write_text("#!/bin/sh\nexit 0\n")
            tool.chmod(0o700)
        self.checkpoint={}
        self.engines=[]
        for kind,engine in (("voice_synthesize","chatterbox_multilingual_mlx"),
                            ("ltx_animate","ltx_2_3_mlx")):
            model=self.primary/(kind+"_weights.bin")
            model.write_bytes(("mock-weight:"+kind).encode())
            self.checkpoint[kind]=model
            manifest=self.primary/(kind+"_manifest.json")
            manifest.write_text(json.dumps({
                "schema_version":1,"kind":kind,"engine":engine,
                "platform":"Darwin","arch":"arm64",
                "minimum_memory_gib":32,"network_required":False,
                "checkpoints":[{"role":"main","path":str(model),"sha256":sha(model)}]
            }))
            self.engines.append({"kind":kind,"path":str(manifest),"sha256":sha(manifest)})
        self.plan=self.primary/"mac_assets.json"
        self.data={
            "schema_version":1,
            "private_roots":[str(self.primary),str(self.other)],
            "assets":[{"role":role,"path":str(f),"sha256":sha(f)}
                      for role,f in self.assets.items()],
            "tools":[{"role":role,
                      "path":str(self.mock_ffmpeg if role=="ffmpeg" else
                                 self.mock_ffprobe if role=="ffprobe" else
                                 self.interpreter),
                      "sha256":sha(self.mock_ffmpeg if role=="ffmpeg" else
                                   self.mock_ffprobe if role=="ffprobe" else
                                   self.interpreter)}
                     for role in ("voice_python","ltx_python","ffmpeg","ffprobe")],
            "engine_manifests":self.engines,
            "minimum_free_gib":20,
        }
        self.save()

    def save(self):
        self.plan.write_text(json.dumps(self.data),encoding="utf-8")

    def run_contract(self):
        return check_mac_contract(
            self.plan,system="Darwin",arch="arm64",
            memory_bytes=48*1024**3,free_bytes=110*1024**3)

    def test_two_roots_and_two_models_are_pinned_but_not_run(self):
        result=self.run_contract()
        self.assertEqual(result["status"],
                         "PINNED_LOCAL_MAC_ASSETS_VERIFIED_ENGINES_NOT_RUN")
        self.assertEqual(len(result["engine_qualification"]),2)
        self.assertFalse(result["real_tts_or_video_run_performed"])
        self.assertFalse(result["voice_and_model_license_validated"])
        self.assertFalse(result["publication_authorized"])
        self.assertNotIn(str(self.root),json.dumps(result))
        self.assertNotIn("password",json.dumps(result).lower())

    def test_changed_bunny_source_rejected(self):
        self.assets["bunny_reference"].write_bytes(b"replaced image")
        with self.assertRaises(MacIntakeError):
            self.run_contract()

    def test_model_bytes_changed_rejected(self):
        self.checkpoint["ltx_animate"].write_bytes(b"tampered model")
        with self.assertRaises(EngineQualificationError):
            self.run_contract()

    def test_wrong_platform_and_low_disk_rejected(self):
        with self.assertRaises(EngineQualificationError):
            check_mac_contract(self.plan,system="Linux",arch="aarch64",
                memory_bytes=48*1024**3,free_bytes=110*1024**3)
        with self.assertRaises(MacIntakeError):
            check_mac_contract(self.plan,system="Darwin",arch="arm64",
                memory_bytes=48*1024**3,free_bytes=2*1024**3)

    def test_missing_wrapper_role_and_relative_path_rejected(self):
        self.data["assets"]=[
            r for r in self.data["assets"] if r["role"]!="ltx_wrapper"]
        self.save()
        with self.assertRaises(MacIntakeError):
            self.run_contract()
        self.data["assets"].append({
            "role":"ltx_wrapper","path":"../untrusted.py","sha256":"a"*64})
        self.save()
        with self.assertRaises(MacIntakeError):
            self.run_contract()

    def test_manifest_rewrite_and_git_root_rejected(self):
        self.plan.write_text("{}")
        with self.assertRaises(MacIntakeError):
            self.run_contract()
        self.save()
        (self.primary/".git").mkdir()
        with self.assertRaises(ValueError):
            self.run_contract()

    def test_python_masquerading_as_ffmpeg_is_rejected(self):
        wrong=next(tool for tool in self.data["tools"] if tool["role"]=="ffmpeg")
        wrong["path"]=str(self.interpreter)
        wrong["sha256"]=sha(self.interpreter)
        self.save()
        with self.assertRaises(MacIntakeError):
            self.run_contract()

    def test_cli_config_does_not_create_run_folders(self):
        self.run_contract()
        self.assertFalse((self.primary/"outputs").exists())
        self.assertFalse((self.primary/"studio.sqlite").exists())


if __name__=="__main__":
    unittest.main()
