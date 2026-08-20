# h3_edl_window

Three small ComfyUI nodes that let a graph read a frame-EDL plan
(`pipeline/plan_windows.py` → `plan.json`) and hand the numbers to the nodes
that already exist.

**This is a NEW package. It does not touch `h3_seam_kit`.** Nothing here is a
copy, a fork or a re-implementation of the live kit — the pinning, the audio
crop and the frame extraction all stay where they are.

## The nodes

| Node | Does | Feeds |
|---|---|---|
| `H3EDLWindow` | reads one window from `plan.json` | `length` → `MiniMaxH3SeamToVideo.length`; `offset_s` / `duration_s` → `SongWindow`; `seed` → `RandomNoise`; `prompt` → the seam node |
| `H3EDLStill` | loads a window's inject still as pixels, unresized | `MiniMaxH3SeamToVideo.first_frame` / `.last_frame` |
| `H3EDLSeamCheck` | asserts two images are the same pixels | audit only — proves window N's last still is window N+1's first |

They exist for exactly one reason: the installed kit cannot read a plan JSON.
Everything else is delegated.

- Audio cropping is **`SongWindow`** (live kit). Not re-implemented here.
- First/last pinning is **`MiniMaxH3SeamToVideo`** (live kit). Not
  re-implemented here.
- Pulling a frame back out of a rendered mp4 is **`SeamFrame`** (live kit). Not
  re-implemented here.

Registered names (`H3EDL*`) cannot collide with the live kit's names; a test in
this repo parses `h3_seam_kit/__init__.py` and asserts the two mapping key sets
are disjoint, so neither package can shadow the other.

### `H3EDLWindow`

| Input | Type | Notes |
|---|---|---|
| `plan_path` | STRING | absolute path to `plan.json` |
| `window_id` | INT | 1-based, matches `windows[].id` in the plan |
| `take` | INT (optional) | non-zero reseeds: `1000 + id*977 + take*7919`, the same policy as `run_chunk.py` |

Outputs: `length` (INT), `offset_s` (FLOAT), `duration_s` (FLOAT), `seed` (INT),
`prompt` (STRING — shot text + camera clause + style block), `first_still`
(STRING), `last_still` (STRING), `window_count` (INT), `summary` (STRING).

### `H3EDLStill`

| Input | Type | Notes |
|---|---|---|
| `plan_path` | STRING | |
| `window_id` | INT | |
| `which` | COMBO | `first` / `last` |
| `input_dir` | STRING (optional) | defaults to ComfyUI's input dir via `folder_paths` |

Outputs: `image` (IMAGE), `path` (STRING), `sha256` (STRING).

Opens the PNG, converts to RGB, normalises to float — and stops. No resize, no
crop, no VAE round-trip, so the pixels that land on frame 0 are the pixels the
previous window was told to end on. If the still's size does not match the
plan's canvas it prints a warning, because `MiniMaxH3SeamToVideo` will rescale a
mismatched image and the join stops being pixel-identical.

The `sha256` output is the cheap proof: run it on window N `last` and window
N+1 `first` and the two strings must match.

### `H3EDLSeamCheck`

Takes two IMAGEs, compares max absolute delta against `tolerance` (default 0.0),
raises on mismatch (`on_mismatch: error`) or prints and passes through
(`warn`). Returns the first image plus a report string.

## Wiring

```
H3EDLWindow(plan.json, window_id)
   ├─ length ─────────────────────────────────► MiniMaxH3SeamToVideo.length
   ├─ prompt ─────────────────────────────────► MiniMaxH3SeamToVideo.prompt
   ├─ offset_s, duration_s ──► SongWindow ─────► MiniMaxH3SeamToVideo.ref_audio_1
   └─ seed ───────────────────────────────────► RandomNoise.noise_seed

H3EDLStill(window_id, "first") ────────────────► MiniMaxH3SeamToVideo.first_frame
H3EDLStill(window_id, "last")  ────────────────► MiniMaxH3SeamToVideo.last_frame
LoadImage(character sheets) ───────────────────► MiniMaxH3SeamToVideo.ref_image_1..4

UNETLoader ─► LoraLoaderModelOnly (FL2V 8-step) ─► MiniMaxH3SigmaShift ─► BasicGuider
```

`SongWindow` needs the master wav visible under ComfyUI's `input/`, since
`LoadAudio` only sees that directory. Copy or hard-link it there once — do not
pre-render a click track, and do not re-encode.

`pipeline/plan_windows.py --emit-graph DIR` writes this exact graph per window
in API format if you would rather submit than click.

## Install on Behem

The live kit at `C:\ComfyUI\custom_nodes\h3_seam_kit\` is **not** a sync target
and must not be overwritten or diffed against this repo. This package goes
beside it as a new folder:

```
xcopy /E /I comfy_nodes\h3_edl_window C:\ComfyUI\custom_nodes\h3_edl_window
```

Then restart ComfyUI. Result:

```
C:\ComfyUI\custom_nodes\
  h3_seam_kit\      <- untouched, still the live kit
  h3_edl_window\    <- new
```

No new pip dependencies: stdlib plus the `torch` / `numpy` / `PIL` that ComfyUI
already ships, and those are imported inside the node functions so the package
also loads in a bare python for tests. Written against ComfyUI 0.3-era node
conventions (`INPUT_TYPES` / `RETURN_TYPES` / `FUNCTION` / `CATEGORY` /
`IS_CHANGED`), matching the 0.30.0 install.

## Tests

Covered by `tests/test_edl_plan.py` in this repo — plan reading, still
resolution, seam identity by sha256, the Comfy class contract, and a check that
these node names cannot shadow the live kit's. No GPU, no torch, no Comfy.
