# ENHANCE_SPEC.md — Prompt Enhancement Spec (for external AIs)

This is the exact spec the MCGrinder enhancer follows. When you (an external AI)
enhance prompts for this pipeline, follow it to spec — the model (MiniMax H3)
was trained on this structure, and the settings choices matter.

## Director modes (pick per shot)

- **auto** — official 3-field structure with timed cuts.
- **punchy-cut** — the user's lines ARE the shot list, kept near-verbatim:
  `[cut]` separators, camera-move-first action lines, per-beat `(Ends 00:SS.SSS)`
  end markers (strictly increasing, last = clip length), one `Audio:` line at
  the end. Best for comedy/action beats.
- **cinematic** — official 3-field + named camera moves (crane, dolly, anamorphic
  push) with amplitude+speed; style stated in texture terms.
- **music-video** — cuts on an implied beat grid, motion choreographed to rhythm,
  `non_diegetic_music` REQUIRED.
- **storybook** — hand-drawn ink/watercolor, gentle camera moves, narration beats.

## The official 3-field structure (auto/cinematic/music-video/storybook)

```
[instruction line if refs are involved]

integrated_multimodal_description: style header, then [Shot 1] ... (no timestamp),
then [Shot N] At 00:SS.SSS, the camera cuts to ...

overall_soundscape: ambient + action sound.
non_diegetic_music: background music (or N/A).
```

## Dialogue (ON by default)

- Speaker IDs `(S1) (S2) ...` — stable across shots; lines in
  `<d>[English] text</d>`.
- If the user asks for no dialogue (or a scene has no speakers), omit it.
- Dialogue OFF: action/visuals/sound only; mouths stay closed.

## Duration awareness

The target length is given. Every timestamp must be strictly inside it; if the
user's beats exceed the length, compress to the strongest beats. The final shot
ends at the clip length. (Punchy-cut: end each beat with `(Ends 00:SS.SSS)`.)

## Style language rules (critical — the model has a retouched-plastic bias)

- NEVER: "vibrant, warm color grading", "crisp lighting", "high quality",
  "sharp", "polished", "cinematic grade".
- DO use texture/material language: "visible skin texture with pores", "natural
  film grain", "soft natural window light", "slight color unevenness",
  "dry-brush watercolor", "loose ink linework".
- Motion: photographic vocabulary ("fast shutter speed, crisp per-frame motion").
- Pick ONE coherent medium per scene. Mixed media (a cartoon character in a
  live-action scene) is fine only when the contrast is the point — name BOTH
  media and frame it as comedy.
- Cross-universe characters: describe their LOOK, not just names
  ("Kramer from Seinfeld in his bowling shirt", "Leela with her single eye and
  purple hair").

## Constraints that always apply

- No on-screen text unless explicitly requested.
- No lip-sync unless the character is the singer (mouths neutral otherwise).
- Keep characters consistent across shots.
- Keep every concrete detail the user gave; don't invent major new elements.

## Ref2VA mode (reference assets attached — 6-section format)

When reference images/videos/audio are attached (character sheets, panels, locations),
use the official Ref2VA 6-section format (H3-Context-IR replica, from
benjiyaya/Minimax-H3-Prompt-AgentSkill, adopted 2026-08-06):

1. **subject_definitions** — one line per tracked reference: `<Subject N>` for reusable
   visible content (bind the assets: "…whose appearance comes from <Picture 1> and whose
   walking motion comes from <Video 1>"), `<Picture N>` ONLY for concrete frame anchors,
   `<Audio N>` for audio roles (voice timbre, music style, beat).
2. **summary** — one paragraph starting with a task-type prefix in square brackets:
   `[keyframe completion]` (image is a frame anchor), `[reference generation]` (assets
   guide generation), `[video editing]`, `[video continuation]`, `[audio reuse]`,
   `[audio reference]` — combined with `+` when several apply, never repeated.
3. **retention_analysis** — one line per label, fixed markers only:
   `fully_preserved | partially_preserved | attribute_transfer | weak_reference`
   (visual); `fully_copy | partially_copy | reference | weak_reference` (audio).
4. **detailed_description** — the timed multi-shot body, 350-500 English words.
5. **overall_soundscape** — 1-4 sentences, ambience + action + non-verbal sounds.
6. **non_diegetic_music** — 1-3 sentences: instrumentation/tempo/rhythm only.

## Official keyframe instruction lines (seam chunks)

For chunks with a pinned first frame (i2va/fl2va), open with the EXACT trained template
instead of paraphrases:

- i2va (pinned first frame only):
  `For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.`
- fl2va (pinned first AND last frame):
  `How the reference pictures align with the target video — Picture 1 (from Shot 1) aligns with the 0.00-second mark of the target video; Picture 2 (from Shot N) aligns with the S.SS-second mark of the target video.`

## Per-shot quality bar (every shot)

- Composition: framing + angle named (wide/medium/close-up, eye-level/low/high/overhead).
- Camera motion: type + amplitude + speed in natural English ("pushes in with small
  amplitude at slow speed").
- ONE dominant subject action per shot — never cram multiple actions.
- Environment/lighting cues per shot.
- Sound cue per shot (diegetic); score goes in non_diegetic_music.
