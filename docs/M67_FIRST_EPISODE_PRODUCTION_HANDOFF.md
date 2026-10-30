# M67: First educational episode — production handoff

**Series:** colors-ar / **Episode:** 001 / **Concept:** red / **Duration:** 75 seconds.

## Files and stages

1. `examples/m67_colors_red_episode_001.json`: storyboard with six beats and a single learning objective.
2. `python -m kidsstudio.m67_episode_gate examples/m67_colors_red_episode_001.json`: validates private-only draft.
3. `python -m kidsstudio.m67_production_plan examples/m67_colors_red_episode_001.json --output /private/episode_plan.json`: produces Godot motion plan, audio text, and visual prompts.
4. `python -m kidsstudio.m67_production_handoff --storyboard examples/m67_colors_red_episode_001.json --output /private/episode_assets.json`: creates an asset manifest with unfilled hashes and pending QA.
5. Mac workers must produce **real** `art/beat_XX.png` and `voice/beat_XX.wav` under a private episode directory. Pin each SHA-256 in the manifest; review the actual outputs and set each `visual_qa` and `voice_qa` to PASS only on real evidence.
6. Run `audit_assets(manifest, private_episode_root)` from `kidsstudio.m67_production_handoff`; only `ASSETS_QA_READY_FOR_RENDER` may proceed to a separately reviewed Godot render/FFmpeg audio assembly.
7. Record the resulting real `render/episode_qa_master.mp4`, pin SHA-256, and independently set render QA PASS. `audit_master` checks asset and master integrity. It **does not** create an M8 readiness report or an approved Pi upload plan.
8. Existing production gates (M8/M62/M63/M64/M65) must still validate readiness, owner-approved private-upload plan, LAN transfer and Pi-side verification. Never bypass them.

## Explicitly not implemented in M67

- Generating art with ComfyUI or voice synthesis; these workers require local model selection and runtime qualification.
- Automatically composing the six storyboard beats into a final mixed audiovisual video. The existing Godot exporter takes a rig and motion scene, not these scene-specific props; a separate scene compositor is required.
- Live dashboard integration, automatic upload, public publishing, or owner approval.
- Physical Mac/Pi acceptance. CI test execution must be checked separately.

## Safety and educational review

Use age-appropriate uncluttered scenes and clear narration. Verify color appearance and contrast on actual video frames, sound loudness, rights, and learning objective. No external links or QR in this episode's child-facing frames. Keep YouTube visibility PRIVATE pending owner review.
