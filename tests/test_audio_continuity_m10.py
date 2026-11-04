"""M10 synthetic PCM envelope analysis; no calls to GPU, API or real FFmpeg."""
from __future__ import annotations

from array import array
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

from kidsstudio.audio_continuity import (
    RATE,WINDOW,compare_voice_to_a2v,AudioContinuityError
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pcm(amplitudes):
    arr=array("h")
    for amplitude in amplitudes:
        arr.extend([int(amplitude)]*WINDOW)
    return arr


class AudioLineageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()
        self.voice=self.root/"approved.wav"
        self.video=self.root/"generated.mp4"
        self.voice.write_bytes(b"synthetic test input voice")
        self.video.write_bytes(b"synthetic mp4 bytes")
        self.ref=[1000+(i*37%103)**2 for i in range(230)]
        self.match=[self.ref[0]]*3+self.ref[:-3]
        self.mismatch=[1000+(i*61%103)**2 for i in range(230)]

    def compare(self, out):
        def fake(path,exe):
            return pcm(self.ref if path==self.voice else out)
        return compare_voice_to_a2v(
            self.voice,self.video,
            voice_sha256=sha(self.voice),a2v_sha256=sha(self.video),
            ffmpeg=sys.executable,decoder=fake)

    def test_lagged_same_audio_energy_passes_but_lip_sync_not_proven(self):
        result=self.compare(self.match)
        self.assertEqual(result["status"],
                         "AUDIO_ENVELOPE_COMPATIBLE_HUMAN_QA_REQUIRED")
        self.assertGreater(result["envelope_correlation"],0.82)
        self.assertFalse(result["speaker_identity_proven"])
        self.assertFalse(result["audio_content_identity_proven"])
        self.assertFalse(result["lip_sync_verified"])
        self.assertFalse(result["publishing_approved"])

    def test_different_narration_detected(self):
        result=self.compare(self.mismatch)
        self.assertEqual(result["status"],"AUDIO_CONTINUITY_UNVERIFIED")
        self.assertLess(result["envelope_correlation"],0.82)

    def test_silent_audio_is_not_proof(self):
        result=self.compare([0]*230)
        self.assertFalse(result["energy_present"])
        self.assertEqual(result["status"],"AUDIO_CONTINUITY_UNVERIFIED")

    def test_much_shorter_embedded_audio_is_not_proof(self):
        result=self.compare(self.ref[:110])
        self.assertFalse(result["duration_close"])
        self.assertEqual(result["status"],"AUDIO_CONTINUITY_UNVERIFIED")

    def test_changed_voice_sha_rejected_before_decode(self):
        self.voice.write_bytes(b"different voice")
        with self.assertRaises(AudioContinuityError):
            compare_voice_to_a2v(
                self.voice,self.video,voice_sha256="a"*64,
                a2v_sha256=sha(self.video),ffmpeg=sys.executable,
                decoder=lambda p,e:pcm(self.ref))

    def test_reject_non_private_and_missing_ffmpeg(self):
        with self.assertRaises(AudioContinuityError):
            compare_voice_to_a2v(
                self.voice,self.video,voice_sha256=sha(self.voice),
                a2v_sha256=sha(self.video),ffmpeg="/no/such/ffmpeg",
                decoder=lambda p,e:pcm(self.ref))
        untrusted=self.root/"redirect.mp4"
        untrusted.symlink_to(self.video)
        with self.assertRaises(AudioContinuityError):
            compare_voice_to_a2v(
                self.voice,untrusted,voice_sha256=sha(self.voice),
                a2v_sha256=sha(self.video),ffmpeg=sys.executable,
                decoder=lambda p,e:pcm(self.ref))


if __name__=="__main__":
    unittest.main()
