# MCGrinder

**A local, open-weights music-video production machine.**

MCGrinder grinds a song into a bespoke animated music video using
[MiniMax H3](https://huggingface.co/MiniMaxAI/MiniMax-H3) running locally in
ComfyUI. It turns a storyboard + character sheets + locations into a
beat-synced, seam-continuous, fully autonomous render pipeline.

Built for a workflow we call **Ship of Theseus**: get the whole video down as a
rough cut, then re-render only the chunks that aren't right — splicing fresh
takes into the finished piece until it *is* right.

## The core idea

**Respect the beat. Don't lip-sync it.**

Music videos need motion that lands on the music. They rarely need characters
mouthing lyrics. MCGrinder feeds the model a *rhythm-only pulse track* (onset
detection → synthesized percussion at the song's beat positions) as its audio
reference — so shots move with the groove while no one mouths a word. Scenes
with a singer can switch to the raw audio reference per-chunk.

## What it does

- **Chunked generation** — a song is cut into 5–15s chunks on its **beat grid**
  (librosa onset analysis), each rendered independently
- **Exact frame seams** — every chunk's frame 0 is *pinned* to the previous
  chunk's final frame (VAE-keyframe conditioning, not a reference-image hint),
  so shots knit together with true continuity
- **Reference conditioning** — storyboard panels, character sheets and
  locations ride along as `<Picture N>` refs per chunk, with the panel as the
  composition authority
- **Drift-free sync** — every chunk is trimmed to exactly its song window, so
  the real track laid over the concat stays sample-accurate to the end
- **The Theseus loop** — `redo.py` re-renders flagged chunks (fresh seed
  takes, seam-aware chaining), `stitch.py` splices old + new into the cut
- **The honing harness** — `hone.py` renders A/B test configs at low
  resolution to tune prompts, refs and audio treatment fast

## Architecture

```
song + pack (storyboard / characters / locations)
        │
        ▼
 state.json (chunk plan: 20 panels → beat-snapped windows, prompts, refs)
        │
        ▼
 run_chunk.py ──cron/loop──► ComfyUI (MiniMax H3 + h3_seam_kit nodes)
        │                        │  pinned seam frame
        │                        │  pack refs        ──► MiniMaxH3SeamToVideo
        │                        │  pulse/raw audio
        ▼                        ▼
 trimmed chunk mp4s ──► stitch.py ──► final video (real song muxed)
```

### Frame EDL: owning the cut instead of hoping for it

Prompt-led clips let the model decide where a shot begins and ends. The frame
EDL takes that back: every picture change is a row at an exact frame naming a
still we already own, and the planner turns consecutive rows into H3 windows
whose **first and last frames are those stills**. The last frame of window N is
the same file as the first frame of window N+1, so the edit cuts on frames that
were timed to the music instead of wherever the model happened to land.

```bash
python pipeline/plan_windows.py catalog/01-dont-freak          # EDL -> window jobs
python pipeline/plan_windows.py catalog/01-dont-freak --wav "C:/.../song.wav"
```

Windows snap to the 17k+5 lattice (124 / 243 / 362 frames); hits closer together
than 124 frames become smash-cut stills laid over the window that spans them.
Read [`docs/EDL.md`](docs/EDL.md) for the schema, the fit policies and the
worked Don't Freak cut sheet — including why a collage first-frame produced a
legless band and an ignored camera lock.

### The custom node kit (`h3_seam_kit/`)

| Node | Job |
|---|---|
| `MiniMaxH3SeamToVideo` | One-pass conditioning: **pinned** first/last keyframes + reference images + reference audio (stock nodes force a choice; this merges both channels) |
| `BeatPulse` | Song window → rhythm-only pulse track (onsets → kick/click/shaker hits). Motion syncs, nobody lip-syncs |
| `SongWindow` | Crop an audio window + its beat grid |
| `SeamFrame` | Pull the exact last/first frame of a video file |
| `BeatSnapDuration` | Snap a desired shot length onto the beat grid |
| `PromptDoctor` | Assemble prompts from parts (shot + panel authority + beat count + anti-lip-sync clause + style) |

### The EDL node pack (`comfy_nodes/h3_edl_window/`)

| Node | Job |
|---|---|
| `H3EDLWindow` | read one window out of `plan.json` — length, audio offsets, seed, prompt |
| `H3EDLStill` | load that window's inject still as pixels, unresized and un-round-tripped |
| `H3EDLSeamCheck` | prove window N's last frame and N+1's first frame are the same pixels |

A separate package that **feeds** the seam kit rather than replacing it: audio
cropping stays `SongWindow`, pinning stays `MiniMaxH3SeamToVideo`, frame
extraction stays `SeamFrame`. Copy it to `ComfyUI/custom_nodes/h3_edl_window/`
as a new folder and leave the live `h3_seam_kit` alone.

Includes a one-line patch to ComfyUI core
(`patches/model_base_merge.patch`) that fixes a real bug: the stock
`MiniMaxH3.extra_conds` clobbers keyframe latents when refs are also present,
silently dropping the pinned frame.

## Install

1. ComfyUI (≥ 0.30) with the MiniMax H3 open weights
   (`Comfy-Org/MiniMax-H3` — the `pruned_fp8_scaled` diffusion models +
   `nvfp4_awq` text encoder), Sage Attention optional but recommended
2. `h3_seam_kit/` → `ComfyUI/custom_nodes/h3_seam_kit/`
3. Apply `patches/model_base_merge.patch` to `comfy/model_base.py`
4. `pip install librosa flask websocket-client` into the ComfyUI venv
5. Copy `config.example.json` (or `config.behem.example.json` on Behem) to
   `config.json` and point it at your Comfy install. Pipeline scripts read
   that file. Do not overwrite a live `ComfyUI/custom_nodes/h3_seam_kit`
   from this repo's `h3_seam_kit/` — the GitHub kit is not a sync source.

## Songs and packs

The repo catalogs songs under [`catalog/`](catalog/README.md). Start with
[`catalog/01-dont-freak/`](catalog/01-dont-freak/CANON.md) (locked canon + SCHEMA
`project.json`). Identity stills and the wav stay on the operator box — see that
pack's `OPERATOR.md`. `pipeline/from_pack.py` builds the `state.json` the existing
worker already consumes. Machine paths: copy `config.example.json` or
`config.behem.example.json` to `config.json`.

## Usage

```bash
# 0. materialize state.json from a catalog pack (Don't Freak: catalog/01-dont-freak)
python pipeline/from_pack.py catalog/01-dont-freak

# 1. write the chunk plan (panels → beat-snapped song windows, prompts, refs)
python pipeline/snap_beats.py        # after beat analysis (beats.json)

# 2. run the worker on a loop (cron-friendly; one chunk per invocation)
python pipeline/run_chunk.py

# 3. when a chunk is wrong, re-render just it (fresh seed; --chain carries the seam)
python pipeline/redo.py 3 --chain

# 4. assemble: concat done chunks + mux the real song
python pipeline/stitch.py

# 5. hone prompts/refs fast at low resolution
python pipeline/hone.py hone_batch.json
```

## Roadmap

- **Stems support** — feed vocal / instrumental stems per scene; compose with
  or without vocals as the shot needs
- **Retimer** — hand the machine a list of exact cut timestamps; it re-snaps
  the chunk plan and marks only the affected chunks for redo
- **Hosted backend adapter** — same chunk plan, OpenRouter/MiniMax API
  execution (2K, ~8× faster) for look-dev and hero shots
- **Pack generation agents** — storyboards, character sheets and locations
  generated by LLM agents from a song's lyrics

## License

Code: MIT. The MiniMax H3 model weights are under MiniMax's H3 community
license — see the model card.


## Speed stack & known issues

**Full-res timing is honest physics, not a bug.** A 1344x768 ref2va clip at 15s (~362 frames) samples at ~45 s/step; a 5s T2V (124 frames) at ~16 s/step — near-perfect linear scaling, and already faster than the reference baseline (NVIDIA's Sol Engine page measures ~20.9 s/step for 124 frames on a 5090). Model loads are ~9 s on NVMe.

**Diagnosed, not broken:** mid-run slowdowns track system-RAM pressure (32 GB box vs a ~42 GB weight stack). More RAM is the single biggest lever.

**Sol Engine** (NVIDIA, 4.52x on 5090) is not yet public. **Spectrum** (ComfyUI-Spectrum-MiniMax-H3, ~30 percent fewer real evals) engages once patches/model_patcher_wrapper_bridge.py is applied to comfy/model_patcher.py (its wrappers otherwise never reach transformer_options), but has a runtime lifecycle bug on ComfyUI 0.30.0 — leave it out of production workflows until upstream fixes it. **EasyCache** (cross-step cache) is an alternative not yet integrated here.

## Speed stack status (2026-08-06)

- **Sol-Attn** (kijai triton): ~2-3x, verified lossless at tau 1.3.
- **FirstBlockCache** (Sol Engine cache line port, nodes/h3_fbc_node.py): ~2x more
  at threshold 0.25 on 20-step schedules (11/20 steps skipped, clean quality).
  Chain: UNET -> SolAttn -> SigmaShift -> H3FirstBlockCache -> guider/scheduler.
- **Spectrum**: engages with the wrapper-bridge patch but has a lifecycle bug on
  ComfyUI 0.30.0; deferred (adds little on top of Sol+FBC at 20 steps anyway).
- **Latent two-pass upscaler**: artifacts at 0.5 denoise; native res still wins.
  RealESRGAN-style pixel upscale (0.5MP gen + x2) is the untested alternate.
- **Turbo LoRA** (4-step, ~5x): early demo, no ComfyUI support yet — watch.

## Turbo LoRA — shippable recipe (from Blizaine/Maestro v1.6.1, 2026-08-06)

The larryvrh MiniMax-H3-Turbo-Lora (4-step audio-video) is now proven usable:
Maestro ships it as a managed mode with **6 inference steps at LoRA strength 0.70**
(compatible with the FULL First&Last / Omni checkpoints; pruned-model combos are
excluded upstream). Sampling speedup ~3.3x on top of Sol-Attn + FBC. Test recipe
when GPU is free: full-res ref2va, 6 steps, turbo LoRA strength 0.70, A/B vs the
20-step baseline (same seed), judge with qwen3.7-flash.

## Director v2 3-pass refinement (adopted idea)

Instead of one enhancement pass, split the LLM work (for the external-AI blurb loop):
1. screenplay pass — creativity-optimized (write the story/beats freely)
2. shot breakdown pass — structure-optimized (emit the SHOT lines as strict JSON)
3. polish pass — model-guide-injected (apply ENHANCE_SPEC + ref2va format + LoRA notes)
Each pass optimizes what the LLM is asked to do; the blurb stays the interchange.
