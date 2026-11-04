"""M10 optional, owner-controlled technical audio-continuity evidence.

Technical waveform-envelope similarity is NOT literal narration correctness,
speaker identity, lip-sync quality, rights clearance or publication approval.
An imported report is checked against the CURRENT M6 voice and A2V receipts;
owner QA remains a separate explicit decision.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import time

from .episode_assembly import digest, _ensure_private

SHA=re.compile(r"^[a-f0-9]{64}$")


class AudioEvidenceError(ValueError):
    pass


class AudioEvidenceLedger:
    def __init__(self,queue):
        self.queue=queue

    def initialize(self) -> None:
        with self.queue._connection(write=True) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS studio_audio_checks(
                series_id TEXT NOT NULL,
                ordinal INTEGER NOT NULL,
                ltx_job_id TEXT NOT NULL,
                voice_sha256 TEXT NOT NULL,
                a2v_sha256 TEXT NOT NULL,
                report_sha256 TEXT NOT NULL,
                correlation REAL NOT NULL,
                status TEXT NOT NULL,
                created_at REAL NOT NULL,
                PRIMARY KEY(series_id,ordinal,ltx_job_id),
                FOREIGN KEY(series_id,ordinal)
                  REFERENCES studio_episodes(series_id,ordinal)
            )""")

    def register(self,series_id:str,ordinal:int,report_file:str|Path)->None:
        path=Path(report_file).expanduser()
        if not path.is_absolute() or path.is_symlink():
            raise AudioEvidenceError("Audio report must be a private absolute non-symlink JSON.")
        path=path.resolve()
        _ensure_private(path.parent)
        if not path.is_file() or not 0<path.stat().st_size<=40_000:
            raise AudioEvidenceError("Missing or oversized audio evidence.")
        try:
            r=json.loads(path.read_text(encoding="utf-8"))
        except (OSError,ValueError) as exc:
            raise AudioEvidenceError("Invalid audio continuity JSON.") from exc
        fields={"schema_version","status","voice_sha256","a2v_sha256",
                "voice_seconds","a2v_audio_seconds","duration_close",
                "envelope_correlation","estimated_lag_seconds","energy_present",
                "audio_content_identity_proven","speaker_identity_proven",
                "lip_sync_verified","owner_audiovisual_review_required",
                "publishing_approved"}
        if not isinstance(r,dict) or set(r)!=fields:
            raise AudioEvidenceError("Audio report format mismatch.")
        if (r["schema_version"]!=1 or
            r["status"]!="AUDIO_ENVELOPE_COMPATIBLE_HUMAN_QA_REQUIRED" or
            not isinstance(r["voice_sha256"],str) or not SHA.fullmatch(r["voice_sha256"]) or
            not isinstance(r["a2v_sha256"],str) or not SHA.fullmatch(r["a2v_sha256"]) or
            r["duration_close"] is not True or r["energy_present"] is not True or
            type(r["envelope_correlation"]) not in (float,int) or
            not .82<=r["envelope_correlation"]<=1.0 or
            type(r["estimated_lag_seconds"]) not in (float,int) or
            abs(r["estimated_lag_seconds"])>.6 or
            r["audio_content_identity_proven"] is not False or
            r["speaker_identity_proven"] is not False or
            r["lip_sync_verified"] is not False or
            r["owner_audiovisual_review_required"] is not True or
            r["publishing_approved"] is not False):
            raise AudioEvidenceError("Technical continuity is not independently verified.")
        with self.queue._connection(write=True) as db:
            records=db.execute("""SELECT stage,state,job_id,artifact_sha256,script_sha256
                FROM studio_episode_stages
                WHERE series_id=? AND ordinal=?""",(series_id,ordinal)).fetchall()
            by_kind={row["stage"]:row for row in records}
            voice=by_kind.get("voice_synthesize")
            ltx=by_kind.get("ltx_animate")
            if (voice is None or voice["state"]!="QA_APPROVED" or
                ltx is None or ltx["state"]!="PENDING_QA" or
                voice["script_sha256"]!=ltx["script_sha256"] or
                voice["artifact_sha256"]!=r["voice_sha256"] or
                ltx["artifact_sha256"]!=r["a2v_sha256"]):
                raise AudioEvidenceError("Report not tied to current approved voice and A2V job.")
            prior=db.execute("""SELECT 1 FROM studio_audio_checks
                WHERE series_id=? AND ordinal=? AND ltx_job_id=?""",
                (series_id,ordinal,ltx["job_id"])).fetchone()
            if prior:
                raise AudioEvidenceError("Audio evidence already recorded for this LTX render.")
            db.execute("""INSERT INTO studio_audio_checks
                (series_id,ordinal,ltx_job_id,voice_sha256,a2v_sha256,
                 report_sha256,correlation,status,created_at)
                VALUES (?,?,?,?,?,?,?,?,?)""",(
                series_id,ordinal,ltx["job_id"],r["voice_sha256"],
                r["a2v_sha256"],digest(path),r["envelope_correlation"],
                "TECH_COMPATIBLE_OWNER_LIPSYNC_REVIEW_PENDING",time.time()
            ))

    def snapshot(self)->list[dict]:
        with self.queue._connection() as db:
            return [dict(row) for row in db.execute("""SELECT c.series_id,
               c.ordinal,c.ltx_job_id,c.status,c.correlation
               FROM studio_audio_checks c
               JOIN studio_episode_stages s
                 ON s.series_id=c.series_id AND s.ordinal=c.ordinal
                 AND s.stage='ltx_animate' AND s.job_id=c.ltx_job_id
               ORDER BY c.series_id,c.ordinal""")]
