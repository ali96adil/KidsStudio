# Narration QA — integration contract

Status: offline text comparison implemented; Whisper audio adapter not yet connected.

## Flow
1. Obtain the immutable approved script from private artifact storage.
2. Produce voice/audio on Mac.
3. Transcribe the exact WAV using an installed local speech-to-text engine (future adapter).
4. Compare recognized text with the approved script using `compare_transcript`.
5. Persist script hash, audio hash, transcript, WER and reviewer status outside Git.
6. Any mismatch, empty text, engine failure or unsupported language -> REVIEW_REQUIRED.
7. Even a TEXT_MATCH_CANDIDATE is **not** approval for publication: independently review audio quality, pronunciation, child safety and educational correctness.

## Constraints
- No external speech upload by default.
- Arabic and English are checked independently.
- Do not auto-rewrite the approved script to match a bad voice take.
- Do not change existing Mac media worker allowlist until dedicated recipes and at-most-once journal tests are complete.
- The existing private-upload human review gate remains mandatory.

## Next acceptance tests
- Local Whisper on WAV: Arabic, English, silence, noisy speech.
- Word timings and subtitles.
- Persist transcript provenance with the episode.
- Test failed transcription and retry without duplicate rendering.
