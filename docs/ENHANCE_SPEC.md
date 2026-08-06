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
