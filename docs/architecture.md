# Architecture

MCGrinder renders a music video as a sequence of independent 5–15s chunks,
each one a single H3 generation, then assembles them. Independence is what
makes the Ship of Theseus loop possible: any chunk can be re-rendered in
isolation and spliced back in.

## The chunk plan (`state.json`)

The plan is the machine's memory. One entry per chunk:

- `offset_s` / `duration_s` — the chunk's window in the song, **snapped to the
  beat grid** so every cut lands on a beat
- `first_frame` — either a pack image (chunk 1) or `"prev_last"` (the previous
  chunk's final frame)
- `refs` — pack sheets (storyboard panel first, then characters/locations)
- `prompt` — shot description + `<Picture N>` assignments + style
- `prompt_override` / `refs_override` / `audio_mode` — per-chunk fixes applied
  without touching the base plan (this is how redos and honing feedback land)
- `status` — `pending / rendering / done / failed`
- `redo` — fresh-seed take counter

The worker advances the plan one step per invocation, so it is safe to drive
from a cron heartbeat at any cadence.

## Why a custom node (`MiniMaxH3SeamToVideo`)

Stock ComfyUI offers two H3 nodes that are mutually exclusive in practice:

- `MiniMaxH3ImageToVideo` — pins exact first/last **keyframes**, but takes no
  reference images or audio
- `MiniMaxH3ReferenceToVideo` — takes reference images + audio, but cannot pin
  a frame

A music video needs all three: exact seams *and* style/character refs *and*
the song. The seam node merges the two conditioning channels (keyframes +
refs) in one pass. Two supporting facts make it work:

1. The model's `PackedLayout` already builds positions for both segment types
   — the DiT accepts them together.
2. `extra_conds` had a bug that dropped keyframe latents when refs were
   present; the patch in `patches/` fixes it (merge, don't clobber).

The seam frame is deliberately **not** tokenizer-tagged: only the pack refs
get `<Picture N>` tags, so prompt assignments map 1:1 to the sheets. (The
naive approach of passing the seam as `ref_image_0` steals the `<Picture 1>`
tag and silently shifts every assignment — the bug that motivated this.)

## Beat, not lipsync (`BeatPulse`)

The audio reference is what makes H3 move to music — and what makes it
mouth words. `BeatPulse` replaces the raw song window with a synthesized
pulse track (onset detection → percussion hits at beat positions). The model
gets rhythm without vocals: motion lands on the beat, nobody lip-syncs.
Singer scenes pass the raw window instead (per-chunk `audio_mode`).

## Drift control

Two compounding errors are handled explicitly:

- **Frame-grid rounding** — H3 renders on a 17k+5 frame grid; a 13.75s window
  renders 14.38s of video. Untrimmed, that drift compounds (+7.5s by the end
  of a 20-chunk video). Every chunk is trimmed to exactly its song window on
  completion.
- **Token-tag shifts** — avoided by keeping the seam untagged (above).

## The loop

```
cron (45m) ──► run_chunk.py ──► submit/poll/trim ──► state.json
                                      │
                              ┌───────┴────────┐
                              ▼                ▼
                         redo.py          stitch.py
                   (flag chunks,      (concat + real-song
                    fresh takes)        mux, sub-second)
```
