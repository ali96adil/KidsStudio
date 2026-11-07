"""Offline PCM voice-presence tests; only synthetic waveforms."""
from __future__ import annotations

from array import array
from pathlib import Path
import tempfile
import unittest
import wave

from kidsstudio.audio_pcm_energy import (
    AudioPresenceError, check_six_beat_pcm_energy,
)


class AudioPCMBeatTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "private"
        self.root.mkdir(mode=0o700)
        self.audio = self.root / "test.wav"

    def write(self, *, silent_beat=None, amplitude=900,
              seconds=24, channels=1, width=2, rate=16000):
        # 0.2 s at the beginning of every 4s beat with a real oscillation;
        # not voice, just enough to test signal-presence counting.
        with wave.open(str(self.audio), "wb") as wav:
            wav.setnchannels(channels)
            wav.setsampwidth(width)
            wav.setframerate(rate)
            for beat in range((seconds + 3) // 4):
                samples = array("h", (
                    amplitude if (silent_beat != beat and
                                  (idx % rate) < rate // 5 and
                                  idx % 2 == 0) else
                    -amplitude if (silent_beat != beat and
                                   (idx % rate) < rate // 5 and
                                   idx % 2 == 1) else 0
                    for idx in range(min(4, seconds - beat * 4) * rate)
                ))
                # Our test is run on little-endian CI/macOS architectures.
                wav.writeframes(samples.tobytes())
        self.audio.chmod(0o600)

    def check(self):
        return check_six_beat_pcm_energy(
            root=str(self.root), relative_path="test.wav")

    def test_six_original_beats_have_energy(self):
        self.write()
        result = self.check()
        self.assertEqual(result["status"],
                         "SIX_BEAT_PCM_ENERGY_PRESENT_UNREVIEWED")
        self.assertEqual(result["beat_count"], 6)
        self.assertFalse(result["speech_words_verified"])
        self.assertFalse(result["arabic_pronunciation_reviewed"])
        self.assertFalse(result["publication_approved"])

    def test_missing_one_beat_fails_for_each_position(self):
        for beat in range(6):
            with self.subTest(beat=beat):
                self.write(silent_beat=beat)
                with self.assertRaises(AudioPresenceError):
                    self.check()

    def test_entirely_silent_track_rejected(self):
        self.write(amplitude=0)
        with self.assertRaises(AudioPresenceError):
            self.check()

    def test_extremely_low_energy_rejected(self):
        self.write(amplitude=150)
        with self.assertRaises(AudioPresenceError):
            self.check()

    def test_short_and_long_audio_rejected(self):
        for duration in (20, 28):
            with self.subTest(duration=duration):
                self.write(seconds=duration)
                with self.assertRaises(AudioPresenceError):
                    self.check()

    def test_stereo_track_rejected(self):
        self.write(channels=2)
        with self.assertRaises(AudioPresenceError):
            self.check()

    def test_public_audio_file_rejected(self):
        self.write()
        self.audio.chmod(0o644)
        with self.assertRaises(ValueError):
            self.check()

    def test_symlink_audio_file_rejected(self):
        self.write()
        (self.root / "linked.wav").symlink_to(self.audio)
        with self.assertRaises(ValueError):
            check_six_beat_pcm_energy(
                root=str(self.root), relative_path="linked.wav")

    def test_invalid_wave_rejected(self):
        self.audio.write_bytes(b"not a WAV")
        self.audio.chmod(0o600)
        with self.assertRaises(AudioPresenceError):
            self.check()

    def test_does_not_modify_source_or_emit_audio(self):
        self.write()
        original = self.audio.read_bytes()
        report = self.check()
        self.assertEqual(self.audio.read_bytes(), original)
        self.assertNotIn("test.wav", str(report))
        self.assertNotIn(str(self.root), str(report))


if __name__ == "__main__":
    unittest.main()
