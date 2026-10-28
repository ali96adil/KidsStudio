"""M29 actual FFmpeg media evidence and fake-Whisper CLI protocol tests.

FFmpeg/FFprobe process a real short H.264 MP4 here. ASR CLI is a
synthetic executable fixture: these tests DO NOT prove Whisper inference,
local installed models, or actual model quality.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import wave
import struct
import math

from kidsstudio.real_media_evidence import (
    capture_asr,capture_frames,EvidenceCaptureError,digest,PNG
)


class RealEvidence29(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="kidsstudio-m29-")
        self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name).resolve()
        self.ffmpeg=shutil.which("ffmpeg")
        self.ffprobe=shutil.which("ffprobe")
        self.assertTrue(self.ffmpeg and self.ffprobe)
        self.ffmpeg=str(Path(self.ffmpeg).resolve())
        self.ffprobe=str(Path(self.ffprobe).resolve())
        self.wav=self.base/"audio.wav"
        with wave.open(str(self.wav),"wb") as w:
            w.setnchannels(1)
            w.setframerate(16000)
            w.setsampwidth(2)
            w.writeframes(b"".join(struct.pack("<h",
                round(9000*math.sin(2*math.pi*440*i/16000)))
                for i in range(16000)))
        self.script=self.base/"source.txt"
        self.script.write_text("هذه الكرة حمراء",encoding="utf-8")
        self.fake_model=self.base/"fake_whisper_model.bin"
        self.fake_model.write_bytes(b"THIS_IS_NOT_A_REAL_MODEL"*50)
        self.fake_whisper=self.base/"fake-whisper-cli"
        self.fake_whisper.write_text(
            "#!"+sys.executable+"\n"
            "import sys\n"
            "from pathlib import Path\n"
            "a=sys.argv\n"
            "assert '-m' in a and '-f' in a and '-of' in a and '-otxt' in a\n"
            "prefix=Path(a[a.index('-of')+1])\n"
            "Path(str(prefix)+'.txt').write_text('هذه الكرة حمراء',encoding='utf-8')\n",
            encoding="utf-8")
        self.fake_whisper.chmod(0o700)
        self.mp4=self.base/"short.mp4"
        subprocess.run([self.ffmpeg,"-hide_banner","-loglevel","error",
            "-nostdin","-y","-f","lavfi","-i",
            "testsrc=size=384x216:rate=15:duration=3",
            "-c:v","libx264","-pix_fmt","yuv420p","-movflags","+faststart",
            str(self.mp4)],timeout=60,check=True,capture_output=True)

    def test_actual_mp4_frame_capture_reuses_immutable_source(self):
        expected=digest(self.mp4)
        result=capture_frames(mp4=self.mp4,expected_mp4_sha=expected,
            ffmpeg_binary=self.ffmpeg,ffprobe_binary=self.ffprobe,
            out_dir=self.base/"frames",frames=3)
        self.assertEqual(result["status"],
                         "REAL_FFMPEG_FRAMES_CAPTURED_NOT_AI_REVIEWED")
        self.assertFalse(result["review_passed"])
        self.assertFalse(result["publication_authorized"])
        self.assertEqual(result["a2v_sha256"],expected)
        self.assertEqual(result["frame_count"],3)
        manifest=Path(result["frames_manifest_file"])
        self.assertEqual(digest(manifest),result["frames_manifest_sha256"])
        document=json.loads(manifest.read_text())
        self.assertEqual(len(document["frames"]),3)
        self.assertEqual(document["a2v_sha256"],expected)
        for frame in document["frames"]:
            p=Path(frame["file"])
            self.assertEqual(digest(p),frame["sha256"])
            self.assertEqual(p.read_bytes()[:8],PNG)
        self.assertEqual(digest(self.mp4),expected)

    def test_bad_source_sha_does_not_capture_or_overwrite(self):
        with self.assertRaises(EvidenceCaptureError):
            capture_frames(mp4=self.mp4,expected_mp4_sha="0"*64,
                ffmpeg_binary=self.ffmpeg,ffprobe_binary=self.ffprobe,
                out_dir=self.base/"blocked",frames=3)
        self.assertFalse((self.base/"blocked").exists())

    def test_bad_frame_count_and_same_output_denied(self):
        expected=digest(self.mp4)
        with self.assertRaises(EvidenceCaptureError):
            capture_frames(mp4=self.mp4,expected_mp4_sha=expected,
                ffmpeg_binary=self.ffmpeg,ffprobe_binary=self.ffprobe,
                out_dir=self.base/"no",frames=13)
        self.assertFalse((self.base/"no").exists())
        out=self.base/"first"
        capture_frames(mp4=self.mp4,expected_mp4_sha=expected,
            ffmpeg_binary=self.ffmpeg,ffprobe_binary=self.ffprobe,
            out_dir=out,frames=3)
        with self.assertRaises(EvidenceCaptureError):
            capture_frames(mp4=self.mp4,expected_mp4_sha=expected,
                ffmpeg_binary=self.ffmpeg,ffprobe_binary=self.ffprobe,
                out_dir=out,frames=3)

    def test_asr_protocol_records_actual_source_and_model_sha(self):
        source_sha=digest(self.wav)
        result=capture_asr(wav=self.wav,script=self.script,
            expected_wav_sha=source_sha,
            expected_script_sha=digest(self.script),
            whisper_binary=str(self.fake_whisper),
            model=self.fake_model,expected_model_sha=digest(self.fake_model),
            out_dir=self.base/"asr",language="ar")
        self.assertEqual(result["status"],
                         "REAL_LOCAL_ASR_EXECUTED_NOT_QA_APPROVED")
        self.assertFalse(result["review_passed"])
        self.assertTrue(result["source_rechecked_after_run"])
        self.assertEqual(result["wav_sha256"],source_sha)
        self.assertEqual(result["transcript_sha256"],
                         digest(Path(result["transcript_file"])))
        self.assertFalse(result["publication_authorized"])

    def test_48k_narration_is_resampled_to_whisper_pcm16(self):
        source=self.base/"highrate.wav"
        with wave.open(str(source),"wb") as w:
            w.setnchannels(1);w.setsampwidth(2);w.setframerate(48000)
            w.writeframes(b"".join(struct.pack("<h",
                round(9000*math.sin(2*math.pi*440*i/48000)))
                for i in range(48000)))
        original_sha=digest(source)
        with self.assertRaises(EvidenceCaptureError):
            capture_asr(wav=source,script=self.script,
                expected_wav_sha=original_sha,
                expected_script_sha=digest(self.script),
                whisper_binary=str(self.fake_whisper),
                model=self.fake_model,expected_model_sha=digest(self.fake_model),
                out_dir=self.base/"requires_conversion",language="ar")
        result=capture_asr(wav=source,script=self.script,
            expected_wav_sha=original_sha,
            expected_script_sha=digest(self.script),
            whisper_binary=str(self.fake_whisper),
            model=self.fake_model,expected_model_sha=digest(self.fake_model),
            ffmpeg_binary=self.ffmpeg,
            out_dir=self.base/"converted",language="ar")
        self.assertEqual(digest(source),original_sha)
        self.assertTrue(result["whisper_input_converted"])
        converted=self.base/"converted"/"whisper_input_pcm16.wav"
        with wave.open(str(converted),"rb") as w:
            self.assertEqual((w.getframerate(),w.getnchannels(),w.getsampwidth()),
                             (16000,1,2))
        self.assertEqual(result["whisper_input_sha256"],digest(converted))

    def test_model_pin_is_mandatory(self):
        with self.assertRaises(EvidenceCaptureError):
            capture_asr(wav=self.wav,script=self.script,
                expected_wav_sha=digest(self.wav),
                expected_script_sha=digest(self.script),
                whisper_binary=str(self.fake_whisper),
                model=self.fake_model,expected_model_sha="f"*64,
                out_dir=self.base/"bad_asr",language="ar")
        self.assertFalse((self.base/"bad_asr").exists())

    def test_asr_missing_executable_fails_closed(self):
        with self.assertRaises(EvidenceCaptureError):
            capture_asr(wav=self.wav,script=self.script,
                expected_wav_sha=digest(self.wav),
                expected_script_sha=digest(self.script),
                whisper_binary=str(self.base/"not_installed"),
                model=self.fake_model,expected_model_sha=digest(self.fake_model),
                out_dir=self.base/"bad_exe",language="ar")


if __name__=="__main__":
    unittest.main()
