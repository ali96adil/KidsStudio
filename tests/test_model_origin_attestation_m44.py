"""M44 immutable owner-attested model origin, not external source verification.

Uses a SYNTHETIC copied Apache header and mock checkpoint. Success
proves byte integrity/HMAC matching only; not copyright clearance.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

from kidsstudio.model_origin_attestation import (
    ModelOriginError,sign_origin_draft,verify_origin,main
)
from kidsstudio.real_media_evidence import digest
from test_model_pilot_probe_m43 import MacProbe43


class ModelOrigin44(unittest.TestCase):
    def setUp(self):
        test=MacProbe43(
            "test_strict_default_checks_every_source_without_starting_a_model")
        test.setUp()
        self.addCleanup(test.doCleanups)
        self.t=test
        self.base=dict(model=test.x.model,model_sha256=test.x.sha)
        self.draft=test.origin_draft
        self.receipt=test.origin_receipt
        self.key=test.origin_key

    def read(self,**kw):
        args=dict(**self.base,receipt=self.receipt,
            receipt_sha256=digest(self.receipt),
            owner_key=self.key)
        args.update(kw)
        return verify_origin(**args)

    def write_draft(self,change):
        doc=json.loads(self.draft.read_text())
        change(doc)
        self.draft.write_text(json.dumps(doc))
        return doc

    def test_owner_signed_receipt_is_local_diagnostic_only(self):
        report=self.read()
        self.assertEqual(report["status"],
            "M44_OWNER_ATTESTED_ORIGIN_BYTES_NOT_INDEPENDENTLY_VERIFIED")
        self.assertEqual(report["checkpoint_package_sha256"],self.t.x.sha)
        self.assertTrue(report["owner_attestation_verified"])
        self.assertFalse(report["upstream_snapshot_independently_verified"])
        self.assertFalse(report["license_legally_adjudicated"])
        self.assertFalse(report["third_party_licenses_verified"])
        self.assertFalse(report["model_quality_qualified"])
        self.assertFalse(report["private_upload_permitted"])
        self.assertFalse(report["public_release_authorized"])
        self.assertNotIn(str(self.t.root),json.dumps(report))

    def test_dry_run_signatures_and_output_never_overwritten(self):
        out=self.t.root/"extra_owner_receipt.json"
        dry=sign_origin_draft(**self.base,draft=self.draft,
            draft_sha256=digest(self.draft),
            owner_key=self.key,out=out)
        self.assertEqual(dry["status"],"M44_OWNER_DRAFT_INSPECTED_NOT_SIGNED")
        self.assertFalse(dry["writes_performed"])
        self.assertFalse(out.exists())
        signed=sign_origin_draft(**self.base,draft=self.draft,
            draft_sha256=digest(self.draft),
            owner_key=self.key,out=out,execute=True)
        self.assertEqual(signed["receipt_sha256"],dry["receipt_sha256"])
        self.assertTrue(out.exists())
        self.assertEqual(verify_origin(**self.base,receipt=out,
            receipt_sha256=digest(out),owner_key=self.key)[
            "owner_attestation_verified"],True)
        with self.assertRaises(ModelOriginError):
            sign_origin_draft(**self.base,draft=self.draft,
                draft_sha256=digest(self.draft),
                owner_key=self.key,out=out,execute=True)

    def test_signer_key_receipt_sha_and_license_mutation_detected(self):
        with self.assertRaises(ModelOriginError):
            self.read(owner_key=b"wrong!"*7)
        with self.assertRaises(ModelOriginError):
            self.read(receipt_sha256="f"*64)
        self.t.license.write_text(self.t.license.read_text()+"MUTATED")
        with self.assertRaises(ModelOriginError):
            self.read()

    def test_3b_forged_7b_and_unreviewed_rights_cannot_sign(self):
        cases=[
            ("upstream_repository","Qwen/Qwen2.5-Omni-3B"),
            ("model_variant","3b"),
            ("license_spdx_claim","Qwen-Research"),
            ("upstream_revision","not-a-commit"),
            ("source_reviewed_by_owner",False),
            ("license_reviewed_by_owner",False),
            ("youtube_private_upload_authorized",True),
            ("public_release_authorized",True),
            ("usage_scope","commercial_youtube_kids"),
        ]
        for key,value in cases:
            with self.subTest(key=key):
                copy_doc=json.loads(self.draft.read_text())
                copy_doc[key]=value
                target=self.t.root/"modified_claim.json"
                target.write_text(json.dumps(copy_doc))
                with self.assertRaises(ModelOriginError):
                    sign_origin_draft(**self.base,draft=target,
                        draft_sha256=digest(target),
                        owner_key=self.key,
                        out=self.t.root/"never_signed.json",execute=True)
                self.assertFalse((self.t.root/"never_signed.json").exists())

    def test_owner_record_authentication_does_not_create_public_permission(self):
        result=self.read()
        self.assertEqual(result["license_spdx_claim"],"Apache-2.0")
        self.assertFalse(result["private_upload_permitted"])
        self.assertFalse(result["public_release_authorized"])


if __name__=="__main__":
    unittest.main()
