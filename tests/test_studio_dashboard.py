"""M5 read-only dashboard and provenance-safe status regression tests."""
from __future__ import annotations

import http.client
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest

from kidsstudio.studio_queue import StudioQueue
from kidsstudio.series_manager import SeriesManager
from kidsstudio.studio_dashboard import build_snapshot, make_handler, stage_timeline
from kidsstudio.studio_orchestrator import StudioOrchestrator


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db=Path(self.temp.name)/"studio.sqlite"
        self.queue=StudioQueue(self.db)
        self.queue.initialize()
        self.registry=SeriesManager(self.queue)
        self.registry.initialize()
        self.registry.create_series("colors-ar","عالم الألوان","ar",[
           {"title":"الأحمر","objective":"تمييز اللون الأحمر"},
           {"title":"الأزرق","objective":"تمييز اللون الأزرق"}
        ],activate=True)

    def test_m32_pinned_plan_is_read_only_and_never_claims_device_ready(self):
        StudioOrchestrator(self.queue).initialize()
        missing=build_snapshot(self.queue)
        self.assertEqual(missing["episodes"][0]["orchestrator"]["state"],"NOT_PINNED")
        self.assertFalse(missing["limits"]["m32_hardware_qualification_ready"])
        with self.queue._connection(write=True) as db:
            db.execute("""UPDATE studio_episodes SET source_sha256=? WHERE
                series_id='colors-ar' AND ordinal=1""",("a"*64,))
            db.execute("""INSERT INTO studio_orchestrator_plans VALUES
                (?,?,?,?,?,?)""",("colors-ar",1,"b"*64,"a"*64,
                "c"*64,self.queue.clock()))
        view=build_snapshot(self.queue)
        ep=view["episodes"][0]["orchestrator"]
        self.assertEqual(ep["state"],"PINNED_SOURCE_CURRENT_FILE_NOT_RECHECKED")
        self.assertFalse(ep["hardware_qualification_ready"])
        self.assertFalse(ep["private_upload_authorized"])
        raw=json.dumps(view,ensure_ascii=False)
        self.assertNotIn("private_models",raw)
        self.assertNotIn("m32-orchestrator-secret",raw)
        with self.queue._connection(write=True) as db:
            db.execute("""UPDATE studio_episodes SET source_sha256=? WHERE
                series_id='colors-ar' AND ordinal=1""",("d"*64,))
        changed=build_snapshot(self.queue)
        self.assertEqual(changed["episodes"][0]["orchestrator"]["state"],
                         "BLOCKED_SCRIPT_CHANGED")

    def test_actual_queue_and_status_without_private_payload(self):
        self.registry.plan_drafts(limit=1)
        self.registry.note("colors-ar","اختبار ملاحظات أمنية",1)
        view=build_snapshot(self.queue)
        self.assertEqual(view["overview"]["episodes_total"],2)
        self.assertEqual(view["overview"]["open_jobs"],1)
        self.assertEqual(view["overview"]["episodes_approved"],0)
        self.assertEqual(view["episodes"][0]["state"],"DRAFT_QUEUED")
        self.assertEqual(view["episodes"][1]["state"],"PLANNED")
        self.assertEqual(view["notes"][0]["text"],"اختبار ملاحظات أمنية")
        self.assertEqual(view["limits"]["voice_and_ltx_tracking"],"NOT_YET_CONNECTED")
        dump=json.dumps(view,ensure_ascii=False)
        self.assertNotIn("auto_review",dump)
        self.assertNotIn("source_sha256",dump)
        self.assertNotIn("artifact_manifest",dump)

    def test_render_receipt_does_not_claim_tts_or_ltx_worked(self):
        stages=stage_timeline("RENDERED_QA_PENDING")
        self.assertEqual(stages[3]["status"],"not_tracked")
        self.assertEqual(stages[4]["status"],"not_tracked")
        self.assertEqual(stages[5]["status"],"not_tracked")
        self.assertEqual(stages[6]["status"],"complete")
        self.assertEqual(stages[7]["status"],"in_review")

    def test_loopback_api_and_read_only_refuse_mutation(self):
        server=ThreadingHTTPServer(("127.0.0.1",0),make_handler(self.queue))
        worker=threading.Thread(target=server.serve_forever,daemon=True)
        worker.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        connection=http.client.HTTPConnection("127.0.0.1",server.server_port,timeout=5)
        try:
            connection.request("GET","/api/overview")
            response=connection.getresponse()
            data=json.loads(response.read())
            self.assertEqual(response.status,200)
            self.assertEqual(data["series"][0]["id"],"colors-ar")
            self.assertEqual(response.getheader("Cache-Control"),"no-store")
            self.assertNotIn("Access-Control-Allow-Origin",dict(response.getheaders()))

            connection.request("GET","/api/acceptance")
            check=connection.getresponse()
            result=json.loads(check.read())
            self.assertEqual(check.status,200)
            self.assertEqual(result["status"],"BLOCKED_LOCAL_SCHEMA_INCOMPLETE")
            self.assertFalse(result["public_release_authorized"])

            connection.request("POST","/api/overview",body=b'{"approve":true}')
            response=connection.getresponse();response.read()
            self.assertEqual(response.status,405)

            connection.request("GET","/api/overview",headers={
                "Host":"attacker.example"})
            response=connection.getresponse();response.read()
            self.assertEqual(response.status,403)

            for resource in ("/","/dashboard.js","/dashboard.css"):
                connection.request("GET",resource)
                response=connection.getresponse()
                content=response.read()
                self.assertEqual(response.status,200,resource)
                self.assertGreater(len(content),200)
        finally:
            connection.close()

    def test_no_storage_auto_initialized_by_snapshot(self):
        self.registry.note("colors-ar","الملاحظات تنحفظ بعد إعادة الفتح")
        second=StudioQueue(self.db)
        result=build_snapshot(second)
        self.assertEqual(result["notes"][0]["text"],
                         "الملاحظات تنحفظ بعد إعادة الفتح")


if __name__=="__main__":
    unittest.main()
