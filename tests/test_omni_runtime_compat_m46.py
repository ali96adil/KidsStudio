"""M46 isolated Mac compatibility probe with NO actual Torch/Transformers weights.

Mocks exercise actual MPS-only scalar and Qwen imports. CI on Linux
cannot prove real MPS hardware availability, license rights or model QA.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from kidsstudio.omni_runtime_compat import (
    RuntimeCompatError,inspect_apple_mps,probe_runtime,main
)
from kidsstudio.real_media_evidence import digest
from kidsstudio.model_package import ModelPackageError
from kidsstudio.model_evidence_readiness import assess_model_evidence, EvidenceReadinessError
from test_model_pilot_probe_m43 import MacProbe43


class FakeScalar:
    def __init__(self,device="mps",value=1.0):
        self.device=SimpleNamespace(type=device)
        self.value=value
    def add(self,number):
        return FakeScalar(self.device.type,self.value+number)
    def cpu(self):
        return self
    def tolist(self):
        return [self.value]


class RuntimeCompat46(unittest.TestCase):
    def setUp(self):
        test=MacProbe43(
            "test_strict_default_checks_every_source_without_starting_a_model")
        test.setUp()
        self.addCleanup(test.doCleanups)
        self.t=test
        self.path=self.t.root/"m46_compat"
        self.kw={"model":self.t.x.model,
                 "model_sha256":self.t.x.sha,
                 "resource_screen":self.t.screen,
                 "out_dir":self.path}

    def importer(self,name):
        class ActualQwenClass:
            @classmethod
            def from_pretrained(cls,*args,**kwargs):
                raise AssertionError("No model/from_pretrained must be called.")
        if name=="torch":
            return SimpleNamespace(
                __version__="2.6.0",
                backends=SimpleNamespace(mps=SimpleNamespace(
                    is_built=lambda:True,is_available=lambda:True)),
                ones=lambda number,device: FakeScalar(device))
        if name=="transformers":
            return SimpleNamespace(__version__="4.52.4",
                Qwen2_5OmniThinkerForConditionalGeneration=ActualQwenClass,
                Qwen2_5OmniProcessor=ActualQwenClass)
        raise AssertionError("Unexpected module import in compatibility probe.")

    def test_true_one_scalar_mps_and_qwen_class_imports_not_model_loading(self):
        with patch.dict(os.environ,{"HF_HUB_OFFLINE":"0",
                                    "TRANSFORMERS_OFFLINE":"0"}):
            record=inspect_apple_mps(system="Darwin",arch="arm64",
                                    loader=self.importer)
            self.assertEqual(os.environ["HF_HUB_OFFLINE"],"1")
            self.assertEqual(os.environ["TRANSFORMERS_OFFLINE"],"1")
        self.assertEqual(record["status"],
                         "M46_MPS_SCALAR_IMPORTS_WORK_MODEL_NOT_LOADED")
        self.assertTrue(record["mps_scalar_arithmetic_passed"])
        self.assertTrue(record["qwen_processor_class_imported"])
        self.assertFalse(record["model_weights_loaded"])
        self.assertFalse(record["model_inference_performed"])
        self.assertFalse(record["model_quality_qualified"])
        self.assertFalse(record["public_release_authorized"])

    def test_linux_cpu_backend_or_broken_qwen_import_rejected(self):
        with self.assertRaises(RuntimeCompatError):
            inspect_apple_mps(system="Linux",arch="x86_64",
                              loader=self.importer)
        def broken_device(name):
            module=self.importer(name)
            if name=="torch":
                module.ones=lambda number,device: FakeScalar("cpu")
            return module
        with self.assertRaises(RuntimeCompatError):
            inspect_apple_mps(system="Darwin",arch="arm64",
                              loader=broken_device)
        def broken_import(name):
            obj=self.importer(name)
            if name=="transformers":
                del obj.Qwen2_5OmniProcessor
            return obj
        with self.assertRaises(RuntimeCompatError):
            inspect_apple_mps(system="Darwin",arch="arm64",
                              loader=broken_import)

    def test_safe_default_has_no_model_worker_calls_or_writes(self):
        def forbidden(*args,**kwargs):
            raise AssertionError("No subprocess allowed during dry-run.")
        snapshot=probe_runtime(**self.kw,launcher=forbidden)
        self.assertEqual(snapshot["status"],"M46_READ_ONLY_RUNTIME_NOT_IMPORTED")
        self.assertFalse(snapshot["mps_scalar_probe_performed"])
        self.assertFalse(snapshot["model_weights_loaded"])
        self.assertFalse(snapshot["public_release_authorized"])
        self.assertFalse(self.path.exists())

    def worker(self,args,**opts):
        self.assertIn("-I",args)
        self.assertIn("--worker",args)
        self.assertEqual(opts["env"]["HF_HUB_OFFLINE"],"1")
        self.assertEqual(opts["env"]["TRANSFORMERS_OFFLINE"],"1")
        self.assertEqual(opts["env"]["PYTORCH_ENABLE_MPS_FALLBACK"],"0")
        self.assertNotIn("KIDS_STUDIO_MODEL_ORIGIN_KEY",opts["env"])
        payload=inspect_apple_mps(system="Darwin",arch="arm64",
                                  loader=self.importer)
        target=Path(args[-1])
        self.assertEqual(target.name,"mps_runtime.json")
        target.write_text(json.dumps(payload))
        target.chmod(0o600)
        return subprocess.CompletedProcess(args,0,b"",b"")

    def test_explicit_bounded_mock_worker_writes_private_no_approval(self):
        report=probe_runtime(**self.kw,execute=True,
                             launcher=self.worker,timeout_seconds=4)
        self.assertEqual(report["status"],
                         "M46_RUNTIME_OBSERVATION_NOT_MODEL_QUALIFICATION")
        self.assertTrue(report["mps_scalar_probe_reported"])
        self.assertTrue(report["files_written"])
        self.assertEqual(report["runtime_report_sha256"],
                         digest(self.path/"mps_runtime.json"))
        self.assertEqual(report["runtime_receipt_sha256"],
                         digest(self.path/"runtime_receipt.json"))
        persisted=json.loads((self.path/"runtime_receipt.json").read_text())
        self.assertEqual(persisted["model_package_sha256"],self.t.x.sha)
        self.assertFalse(persisted["private_upload_permitted"])
        self.assertFalse(persisted["model_weights_loaded"])
        self.assertGreaterEqual(report["elapsed_seconds"],0)
        self.assertFalse(report["model_inference_performed"])
        self.assertFalse(report["mac_pi_hardware_qualified"])
        self.assertFalse(report["model_quality_qualified"])
        self.assertFalse(report["private_upload_permitted"])
        self.assertFalse(report["public_release_authorized"])
        with self.assertRaises(RuntimeCompatError):
            probe_runtime(**self.kw,execute=True,launcher=self.worker)

    def test_m45_inventory_binds_mps_scalar_report_without_claiming_7b_ready(self):
        self.test_explicit_bounded_mock_worker_writes_private_no_approval()
        params=dict(
            model=self.t.x.model,model_sha256=self.t.x.sha,
            origin_receipt=self.t.origin_receipt,
            origin_sha256=digest(self.t.origin_receipt),
            owner_key=self.t.origin_key,
            resource_screen=self.t.screen,
            mps_runtime_receipt=self.path/"runtime_receipt.json",
            mps_runtime_receipt_sha256=digest(self.path/"runtime_receipt.json"),
            mps_worker_report=self.path/"mps_runtime.json",
            mps_worker_sha256=digest(self.path/"mps_runtime.json"),
            mps_python=sys.executable,
        )
        summary=assess_model_evidence(**params)
        self.assertTrue(summary["mps_scalar_report_bytes_checked"])
        self.assertEqual(summary["status"],
                         "M45_EVIDENCE_INVENTORY_NOT_PRODUCTION_READY")
        self.assertEqual(summary["qualified_gate_count"],0)
        self.assertFalse(summary["mac_pi_hardware_qualified"])
        self.assertFalse(summary["model_quality_qualified"])
        self.assertFalse(summary["private_upload_permitted"])
        self.assertFalse(summary["public_release_authorized"])
        runtime=self.path/"mps_runtime.json"
        forged=json.loads(runtime.read_text())
        forged["model_weights_loaded"]=True
        runtime.write_text(json.dumps(forged))
        with self.assertRaises((EvidenceReadinessError,RuntimeCompatError)):
            assess_model_evidence(**{**params,
                "mps_worker_sha256":digest(runtime)})

    def test_forged_worker_model_loaded_or_public_permission_rejected(self):
        def bad(args,**kw):
            self.worker(args,**kw)
            f=Path(args[-1]);doc=json.loads(f.read_text())
            doc["model_weights_loaded"]=True
            f.write_text(json.dumps(doc))
            return subprocess.CompletedProcess(args,0,b"",b"")
        with self.assertRaises(RuntimeCompatError):
            probe_runtime(**self.kw,execute=True,launcher=bad)
        self.assertFalse((self.path/"pilot_authorized.json").exists())

    def test_timeout_or_missing_report_cannot_claim_success(self):
        def timeout(args,**opts):
            raise subprocess.TimeoutExpired(args,1)
        with self.assertRaises(RuntimeCompatError):
            probe_runtime(**self.kw,execute=True,launcher=timeout)
        self.assertFalse((self.path/"mps_runtime.json").exists())

    def test_mutated_checkpoint_during_probe_blocks(self):
        def mutate(args,**opts):
            result=self.worker(args,**opts)
            self.t.x.fixture.weights.write_bytes(
                self.t.x.fixture.weights.read_bytes()+b"changed")
            return result
        with self.assertRaises(ModelPackageError):
            probe_runtime(**self.kw,execute=True,launcher=mutate)

    def test_current_resource_screen_and_timeout_limits_block(self):
        def weak(*,model,expected_model_sha,variant):
            record=self.t.screen(model=model,
                expected_model_sha=expected_model_sha,variant=variant)
            record["status"]="M42_RESOURCE_SCREEN_BLOCKED"
            return record
        with self.assertRaises(RuntimeCompatError):
            probe_runtime(**self.kw,execute=True,resource_screen=weak)
        with self.assertRaises(RuntimeCompatError):
            probe_runtime(**self.kw,timeout_seconds=0,execute=True)
        self.assertFalse(self.path.exists())


if __name__=="__main__":
    unittest.main()
