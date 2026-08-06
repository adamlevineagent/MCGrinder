# The Dialogue Recipe (validated 2026-08-06)

The scripted-dialogue test that "worked really well": Kramer (Seinfeld) + Leela
(Futurama) + Jerry, three speakers, 15 s, 1344x768, punchy-cut prompt with
dialogue ON. This is the current best-known configuration for dialogue scenes.

## The prompt shape that works

- **Punchy-cut format** with the user's beats kept near-verbatim, `[cut]`
  separators, camera-move-first action lines, per-beat `(Ends 00:SS.SSS)`
  markers that strictly increase and end at the clip length, one `Audio:` line.
- **Dialogue ON**: speaker IDs `(S1) (S2) (S3)` with `<d>[English] ...</d>` lines,
  one character voice per ID, tone matched to the user's intent.
- **Committed medium**: mixed-media stated explicitly ("Kramer in live-action
  realism, Leela in 2D animation, the medium contrast played for comedy") — never
  generic gloss ("vibrant, warm, crisp lighting" → plastic look).
- **Texture language**: film grain, soft natural light, slight color unevenness.
- **Character look descriptions** instead of names alone (bowling shirt; single
  eye, purple hair).

## Settings

- 1344x768 native (below-native caps quality — 768² beat 832x480 on the same prompt)
- 20 steps, res_multistep, beta scheduler, Sol-Attn tau 1.3
- T2V (no audio ref) so the model generates the voices itself

## What it costs

- 15 s native ≈ 10-15 min wall with Sol-Attn. The KJNodes preview override costs
  ~2x step time on H3 (its preview path is LTX-gated) — do not add it; use
  MiniMaxH3PreviewOverrideCS (the Director's H3-native node) instead.

## Known limits (the voice question)

H3's generated voices are the weakest output. If voices matter, layer Qwen3-TTS
(clone or designed voice) as the dialogue track: feed it as the chunk's
ref_audio so lips/motion sync, then mux the original TTS audio at stitch time.
