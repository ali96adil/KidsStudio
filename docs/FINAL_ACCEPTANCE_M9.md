# M9 — Final Integration and Acceptance Preparation

STATUS: development only in draft PR #28. No changes were installed on the
owner's Mac/Pi, no real LTX or Chatterbox inference, no model downloads,
paid APIs, video upload, public publication or production file edits.

## 1. Offline database backup and recovery drill

New studio-backup-drill command uses the SQLite online backup API rather than
copying a potentially open WAL-backed DB file. It:

- requires an existing Studio Brain DB and a new private destination outside Git;
- creates a restrictive mode 0600 file with exclusive create (no overwrite);
- checks SQLite full integrity, foreign keys, and rows per table;
- returns SHA256 and aggregate table counts, without exposing private job data;
- leaves failed files in place for deliberate recovery, never retries silently;
- restores only to a throwaway temporary database in the restore drill.
- never overwrites, migrates, pauses or changes the active database.

Future one-time commands (placeholder paths, not to run now):

    studio-backup-drill --source /PRIVATE/studio.sqlite \
      --destination /PRIVATE/backup/studio_snapshot.sqlite

    studio-backup-drill --restore-drill \
      /PRIVATE/backup/studio_snapshot.sqlite

The drill validates the SQLite backup, not loss/recovery of Mac media, model
weights, external credentials, or physically independent backups.

## 2. Unified acceptance inventory

The new studio-acceptance-review CLI is READ-ONLY on the canonical Studio
Brain SQLite database. It checks:
- database integrity, migration tables, exactly one active series;
- contiguous episode curriculum sequence;
- writer and renderer queue provenance, valid media receipt status and SHA;
- M7 quality evidence for the CURRENT completed media job;
- separately recorded voice/LTX stages, script and WAV SHA lineage;
- number of open worker jobs, first approved episode;
- optional existing backup sacrificial restore drill;
- optional immutable episode archive plus private preview readiness.

It returns individual PASS, ACTION, BLOCKED, DEVICE_TEST_REQUIRED, or
HUMAN_REVIEW_REQUIRED findings and a next action for each. It NEVER claims
that the installed Apple Silicon MLX engines or rights were verified by CI.

Future read-only command:

    studio-acceptance-review --db /PRIVATE/studio.sqlite

Optional evidence verification:

    studio-acceptance-review --db /PRIVATE/studio.sqlite \
      --backup /PRIVATE/backup/studio_snapshot.sqlite \
      --archive /PRIVATE/archives/colors-ar/ep001/ep01-v1 \
      --series colors-ar --episode 1

The local read-only dashboard now has an on-demand section named
جاهزية اختبار الإنتاج النهائي. It calls /api/acceptance, not a worker
or publishing endpoint. It does not copy backups or run models.

## 3. Final ONE-PASS device acceptance, later when owner approves

Preparation:
1. Freeze and record Git commit; keep main stable until accepted.
2. Make a test backup and sacrificial restore. Record independent media backup.
3. Check exact Mac-installed Chatterbox multilingual MLX with Bunny voice B,
   LTX-2.3 MLX Q4 with its *actual* wrapper, FFmpeg, Bunny v06/v07 calibration,
   original character/voice assets, GPU RAM, disk and Mac/Pi clock.
4. Hash-pin weights, wrapper code, script and input WAV/A2V. Explicitly inspect
   actual commercial model, reference voice, music, effects and visual rights.
5. Do not silently migrate previous standalone Control Center v1-v3 SQLite.

One real pilot episode, الأرنب والكرة الحمراء:
1. Owner approves the complete educational and Arabic-language script.
2. Chatterbox generates exact scene WAV and owner reviews pronunciation.
3. LTX consumes the exact reviewed WAV and pinned Bunny image reference.
4. Owner reviews all real scene outputs for safe motion, lipsync, identity and
   camera continuity, respecting the original frontal 384x384 v07 limits.
5. Assemble and run FFmpeg full video/audio technical QA against exact MP4 SHA.
6. Review all eleven M7 quality, education, licensing and rights criteria.
7. A failed criterion records CHANGES_REQUESTED, not APPROVED.
8. When approved, build and independently verify the immutable archive,
   check the private-preview release gate and record backup/restore outcome.
9. Any YouTube upload is manually authorized and PRIVATE only at first.
   Public release is a separate owner decision, never implicit.

STOP immediately for:
- drifted Pi/Mac time, stale leases or lost receipt lineage;
- unexpected internet/model downloads, unapproved API spend, keys exposure;
- mismatched SHA256, wrong reference voice, unknown commercial rights;
- broken sound, lip sync, child safety or pedagogy checks;
- missing valid archive, backup or updated-current-render QA;
- any upload or publish attempt without explicit separate owner permission.

Privately retain: Git SHA, engine versions, weights hashes, script/scene SHA,
queue IDs, output WAV/A2V SHA, final MP4 hash, technical and educational
reviews, immutable archive and tested restore evidence. Never upload model
weights, private media, voice samples, keys or owner data to public GitHub.

## 4. Still NOT done

- Real Chatterbox and LTX Mac wrapper/engine qualification and whole real episode
- Full Pi/Mac audiovisual acceptance and rights verification
- Second independent encrypted/offsite backup and restore trial
- Legacy Control Center v1-v3 migration
- Human inspection of final episode and manual/private YouTube preview

All CI tests use synthetic media and/or fake model executors. Successful CI
does not mean the real episode has been produced or approved. Keep PR draft
and do not merge or deploy without the later owner-authorized device test.
