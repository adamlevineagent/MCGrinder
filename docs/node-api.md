# Node API

All nodes live in `h3_seam_kit/` (ComfyUI custom nodes). Registered names
shown as node titles.

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
