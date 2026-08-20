# Node API

Two ComfyUI custom-node packages, installed side by side. Registered names
shown as node titles.

- `h3_seam_kit/` — the generation nodes (pinning, audio, seams). The copy in
  this repo is **not** a sync source for the live install on Behem.
- `comfy_nodes/h3_edl_window/` — three nodes that read a frame-EDL plan and feed
  the kit. New package, new folder, no overlap in registered names.

## MiniMaxH3SeamToVideo

One-pass generation conditioning: **pinned** keyframes + reference images +
reference audio.

| Input | Type | Notes |
|---|---|---|
| `clip` | CLIP | minimax text encoder (nvfp4) |
| `vae` | VAE | video VAE |
| `audio_vae` | VAE | audio VAE |
| `prompt` | STRING | multiline; `<Picture N>` / `<Audio 1>` tags resolve against refs |
| `width` / `height` | INT | multiple of 32; native canvas 1344×768 (768p short edge) |
| `length` | INT | frame count, snapped up to the 17k+5 grid (124 ≈ 5s; 362 ≈ 15s) |
| `ref_image_size` | COMBO | `match` (scale refs to gen area) / `max` (2048 short edge, slower) |
| `first_frame` | IMAGE | optional — **pinned** frame 0 (VAE-keyframe conditioning) |
| `last_frame` | IMAGE | optional — **pinned** final frame |
| `ref_image_1..4` | IMAGE | pack sheets; tagged `<Picture 1..4>` in order |
| `ref_audio_1` | AUDIO | song window (or pulse track); tagged `<Audio 1>` |

Outputs: `positive` (CONDITIONING), `latent` (LATENT) — drop-in for the
standard sampler chain (BasicGuider → SamplerCustomAdvanced).

Notes:
- Keyframes are injected via the conditioning channel and are **not** tagged,
  so `<Picture N>` maps 1:1 to `ref_image_N`.
- Requires the `model_base.py` merge patch (see `patches/`).

## BeatPulse

| Input | Type | Notes |
|---|---|---|
| `audio` | AUDIO | any loaded audio (use SongWindow for a precise crop) |
| `pulse_type` | COMBO | `kick` (sine thump), `click` (noise burst), `shaker` |
| `gain` | FLOAT | 0.1–3.0 |

Outputs: `pulse` (AUDIO, same length/sr), `beat_count` (INT),
`beat_times_json` (STRING — relative beat times).

## SongWindow

| Input | Type |
|---|---|
| `audio` | AUDIO |
| `offset_s` / `duration_s` | FLOAT |

Outputs: `window` (AUDIO crop), `beat_count` (INT), `beat_times_json` (STRING).

## SeamFrame

| Input | Type | Notes |
|---|---|---|
| `video_path` | STRING | absolute path to an mp4 |
| `mode` | COMBO | `last` (default, `-sseof -0.05`) / `first` |

Output: `IMAGE` (1,H,W,3).

## BeatSnapDuration

| Input | Type | Default |
|---|---|---|
| `desired_s` | FLOAT | 14.0 |
| `bpm` | FLOAT | 172.3 |
| `min_s` / `max_s` | FLOAT | 5.0 / 15.0 |

Outputs: `duration_s` (FLOAT, beat-snapped, clamped), `beat_count` (INT).

## PromptDoctor

| Input | Type |
|---|---|
| `shot` | STRING (multiline) |
| `style` | STRING |
| `panel_note` | STRING |
| `audio_note` | STRING (optional) |
| `beat_count` | INT (optional) |
| `anti_lipsync` | BOOLEAN (default true) |

Output: `STRING` — assembled prompt: shot, panel note, "spans N beats",
anti-lip-sync clause, audio note, style block.

# h3_edl_window

Frame-EDL plan → the kit. Full detail in
[`comfy_nodes/h3_edl_window/README.md`](../comfy_nodes/h3_edl_window/README.md)
and [`docs/EDL.md`](EDL.md). Plans come from `pipeline/plan_windows.py`.

## H3EDLWindow

| Input | Type | Notes |
|---|---|---|
| `plan_path` | STRING | absolute path to a `plan_schema` 1 file |
| `window_id` | INT | 1-based, matches `windows[].id` |
| `take` | INT (optional) | non-zero reseeds with the `run_chunk.py` policy |

Outputs: `length` (INT → the seam node's `length`), `offset_s` / `duration_s`
(FLOAT → `SongWindow`), `seed` (INT), `prompt` (STRING), `first_still` /
`last_still` (STRING), `window_count` (INT), `summary` (STRING).

## H3EDLStill

| Input | Type | Notes |
|---|---|---|
| `plan_path` | STRING | |
| `window_id` | INT | |
| `which` | COMBO | `first` / `last` |
| `input_dir` | STRING (optional) | defaults to ComfyUI's input dir |

Outputs: `image` (IMAGE), `path` (STRING), `sha256` (STRING). Loads the inject
still with no resize and no VAE round-trip, so the join stays pixel-identical.

## H3EDLSeamCheck

| Input | Type | Default |
|---|---|---|
| `image_a` / `image_b` | IMAGE | |
| `on_mismatch` | COMBO | `error` / `warn` |
| `tolerance` | FLOAT | 0.0 |

Outputs: `image` (passthrough), `report` (STRING). Audit node: proves window N's
last frame and window N+1's first frame are the same pixels.
