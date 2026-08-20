# Frame EDL → H3 windows

How MCGrinder takes the cut back from the model.

## What went wrong

Don't Freak was first run as prompt-led Ref2VA clips. Two failures, one cause:

- **Legless floating busts.** `00-band-bible-from-portraits.png` is a *collage*:
  waist-up character cutouts arranged on a flat field. Handed to H3 as a first
  frame or a layout it did exactly what it was trained to do — it reproduced the
  frame it was given. Cutouts in, cutouts out, no legs, no floor.
- **"Locked camera" ignored.** The prompt asked for a locked frame and got a
  push-in. The model had no pixel commitment to hold to, only a sentence, and a
  collage of cutouts reads as a tableau you reveal.

Neither is a prompt bug. Both are the same missing thing: **nothing in the graph
said what frame 0 and the final frame must actually be.**

## What replaces it

The EDL owns the cut. Every picture change is a row at an exact frame, and each
row names an **inject still** we already own. The planner pairs consecutive rows
into H3 windows, and each window is generated with a pinned `first_frame` and a
pinned `last_frame`.

That buys three things at once:

1. **The cuts land on the music**, because the frame numbers come from the ear
   and never move.
2. **The camera holds**, because both ends of every window are fixed pixels. 18
   of Don't Freak's 19 windows open and close on the *same* plate, so the shot
   is physically obliged to come back to where it started. Text never had to be
   trusted.
3. **Identity holds**, because the character sheets ride as `<Picture N>` refs
   where they belong instead of as the frame the model copies.

Nothing here replaces the live `h3_seam_kit`. `MiniMaxH3SeamToVideo` already
takes `first_frame` + `last_frame` + four refs + audio in one conditioning pass;
the planner just tells it exactly what to put there.

## Roll or cut

Each row declares what kind of join happens at its frame.

- **`roll`** — the window ends on the *next* row's still. The two windows share
  a frame: the same file, the same bytes, so the join is seamless and the edit
  can drop the duplicate. Use it when the picture genuinely continues.
- **`cut`** — the window ends on its *own* opening still, and the next window
  starts fresh on the new one. The picture change is a hard cut.

`cut` is not a detail. 13 of Don't Freak's 20 joins change the room or who is in
frame — the Unplugged stage to a burning apartment, a sloth alone to the full
band, a green room with a sloth in it to an empty one. Rolling those would pin a
window between two different pictures and ask H3 to get from one to the other
over ten seconds, which is a morph, not a cut. Ending the window on its own
opening plate gives a locked shot *and* a hard cut at the next hit, for free.

The one window that legitimately crosses is #2: it opens on the claws plate and
ends on the sloth standing wide, because that is the 0:11–0:12 jerky zoom-out the
canon asks for. It is the only window not tagged `camera: locked`, and the
planner asserts that relationship — a locked window must be pinned to one plate.

## The lattice, and why the fit is never free

H3 clip lengths sit on the 17k+5 grid. At 24fps the useful ones are:

| frames | seconds | new frames it supplies |
|---|---|---|
| 124 | 5.167 | 123 |
| 243 | 10.125 | 242 |
| 362 | 15.083 | 361 |

A window's last frame is shared with the next window's first frame, so an
`n`-frame window advances the timeline by `n - 1`. Don't Freak's spans are
ear-timed to whole seconds (192, 216, 240, 264, 288, 312, 360, 276 frames), and
none of those are 123, 242 or 361. The lattice and the music do not agree, and
no amount of packing makes them. So the planner picks a policy and *reports the
residual* instead of hiding it:

| `--fit` | rule | residual | Don't Freak cost |
|---|---|---|---|
| `cover` (default) | smallest lattice that reaches the next inject | trim the tail | 6045 frames generated for 5076 used — **19.1% overhead**, zero freezes |
| `under` | largest lattice that stays inside the span | hold the still | 3903 generated, but **1192 frames of freeze** (49.7s) |
| `nearest` | smallest absolute residual | mixed | 4974 generated, 230 trim + 351 hold |

`cover` is the default because a trimmed tail is invisible — the shot is cut
away from before it resolves, and what comes next is the inject still itself, so
the join is a clean match cut. A `hold` is a literal freeze frame. Freezes are
on-style at a smash cut and wrong in the middle of a jam, which is why they are
opt-in per row (`"fit": "under"`) rather than global.

One exception is forced: the final window would run 15.083s past 200.0s and off
the end of a 211.48s wav. Padding the audio would mean inventing audio, so the
planner clamps to the largest lattice the wav can feed (243) and reports the
34-frame hold. On the last shot of the song — a decelerating empty room — a 1.4s
hold on the empty stage is the ending anyway.

## Smash cuts

A hit closer to the previous boundary than `min_fill_frames` (124) cannot open a
window; the shortest clip H3 makes is longer than the gap. Those rows are
`kind: "smash"`: **no H3 window is generated for them.** They are editorial
still inserts cut in over the window that spans them, which is how fast
beat-timed cuts get made anyway.

Don't Freak has exactly one: row 12 at 115.0s (frame 2760), 120 frames before
the next hit. It sits inside window 11, which runs 106.0 → 120.0 as a single
362-frame clip. That is legal because row 11 is tagged `kind: "hold"` — tagging a
span as a hold is what authorises a window to span an intermediate smash. If a
too-close hit appears in a span that is *not* a hold, the planner demotes it
itself and records `auto_demoted: true`.

## `edl.json` — schema v1

```json
{
  "edl_schema": 1,
  "fps": 24,
  "video": {"width": 1344, "height": 768, "lattice": [124, 243, 362]},
  "audio": {"path": "...", "codec": "pcm_s16le", "sample_rate": 48000,
            "channels": 2, "duration_s": 211.479979, "total_samples": 10151039,
            "frames_24": 5076},
  "model": {"turbo_lora": "minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors",
            "steps": 8, "lora_strength": 1.0},
  "defaults": {"camera": "locked", "audio_mode": "raw", "fit": "cover",
               "min_fill_frames": 124},
  "stills": [{"id": "INJ_...", "role": "inject", "body": "standing_full",
              "status": "needed", "comfy_input": "dont_freak/...png",
              "behem": "C:/...", "brief": "what to shoot"}],
  "rows": [{"id": 1, "text": "claws / Unplugged fade-up", "t_sec": 0.0,
            "frame_24": 0, "kind": "inject", "still": "INJ_CLAWS_CU",
            "refs": [], "camera": "locked", "shot": 1, "framing": "cu_plate",
            "source": "adam-ear", "certain": true, "notes": "..."}]
}
```

**Row fields**

| field | meaning |
|---|---|
| `t_sec` / `frame_24` | the cut. `frame_24` must equal `round(t_sec * fps)`; the validator enforces it |
| `kind` | `inject` = window boundary · `hold` = boundary that may span a smash · `smash` = still insert, **no window** · `end` = terminal boundary, opens nothing |
| `transition` | `roll` = the previous window ends on this row's still (shared frame) · `cut` = it ends on its own opening still and this is a hard cut. Absent on row 1, which has no incoming join |
| `still` | id from `stills[]`. Must have `role: "inject"` |
| `refs` | `[]` inherits the catalog shot's refs; non-empty overrides |
| `camera` | `locked` appends the no-move clause to the prompt; anything else is named in the prompt as the only move allowed |
| `shot` | the pack shot id whose `start_s` this row must equal — this is what keeps the EDL from becoming a second timeline |
| `certain` | `false` marks a placeholder (force-align, ear estimate). Surfaces as `uncertain_rows` in the plan |
| `fit` | per-row override of the window fit policy |

**Still fields.** `role` is `inject`, `identity_ref` or `forbidden`. `body` is
`standing_full`, `empty_plate`, `cu_object`, `bust` or `collage`. A cut frame
must be `role: inject` with a `body` of `standing_full`, `empty_plate` or
`cu_object` — so a bust sheet or a collage can never become a first/last frame,
and the validator says so by name. `status` is `on_behem` or `needed`; anything
`needed` comes back in the plan's `needed_stills` shopping list with its brief.

## `plan.json` — what the planner emits

One job per window: `first_still` / `last_still` (as ComfyUI input names),
`nframes`, `span_frames`, `trim_tail_frames` / `hold_tail_frames` (with
`hold_still`, the plate to hold on), `out_transition`, `pin`, `audio_start_s` /
`duration_s` / `audio_start_sample` / `audio_end_sample`, `seed`, `steps`,
`turbo_lora`, `refs`, `prompt_full`, plus `smash_rows` for the inserts the
editor lays over it. Seeds use the same policy as `run_chunk.py`
(`1000 + id*977 + take*7919`), so `--take 1` is a fresh take of every window.

The plan also carries what is wrong with it: `warnings` (a locked window pinned
between two different plates, a span longer than the lattice, refs past the
seam node's four), `needed_stills`, `uncertain_rows`, and a `ready` flag.
`--strict` turns any warning into a non-zero exit.

```bash
python pipeline/plan_windows.py catalog/01-dont-freak
python pipeline/plan_windows.py catalog/01-dont-freak --fit under --stdout
python pipeline/plan_windows.py catalog/01-dont-freak --wav "C:/.../Don't Freak.wav"
python pipeline/plan_windows.py catalog/01-dont-freak \
    --audio-input "dont_freak/Don't Freak.wav" --emit-graph C:/tmp/dont_freak_graphs
```

`--wav` re-probes the real file (stdlib `wave`, PCM) and stamps sample rate,
channels, duration, total samples and `frames_24` into the plan; if the probe
moves the end row it says so rather than moving the cut quietly.
`--emit-graph` writes one ComfyUI API graph per window, wired to the installed
kit: `LoadAudio → SongWindow → MiniMaxH3SeamToVideo.ref_audio_1`, two
`LoadImage` nodes into `first_frame` / `last_frame`, `UNETLoader →
LoraLoaderModelOnly` (FL2V 8-step) → `MiniMaxH3SigmaShift` → sampler at 8 steps.

## Don't Freak, as planned

21 rows → 19 windows + 1 smash cut, covering all 5076 frames.

| # | rows | frames | span | length | fit | join | pinned still(s) |
|---|---|---|---|---|---|---|---|
| 1 | 1→2 | 0–264 | 264 | **362** | trim 97 | roll | CLAWS_CU (locked) |
| 2 | 2→3 | 264–528 | 264 | **362** | trim 97 | roll | CLAWS_CU → SLOTH_STAGE_STAND |
| 3 | 3→4 | 528–816 | 288 | **362** | trim 73 | roll | SLOTH_STAGE_STAND (locked) |
| 4 | 4→5 | 816–1104 | 288 | **362** | trim 73 | **cut** | SLOTH_STAGE_STAND (locked) |
| 5 | 5→6 | 1104–1320 | 216 | **243** | trim 26 | roll | SLOTH_FIRE_STAND (locked) |
| 6 | 6→7 | 1320–1536 | 216 | **243** | trim 26 | **cut** | SLOTH_FIRE_STAND (locked) |
| 7 | 7→8 | 1536–1776 | 240 | **243** | trim 2 | **cut** | SLOTH_HALL_STAND (locked) |
| 8 | 8→9 | 1776–1968 | 192 | **243** | trim 50 | **cut** | SLOTH_STAGE_STAND (locked) |
| 9 | 9→10 | 1968–2280 | 312 | **362** | trim 49 | **cut** | BAND_STAGE_STAND (locked) |
| 10 | 10→11 | 2280–2544 | 264 | **362** | trim 97 | **cut** | CATS_STAGE_STAND (locked) |
| 11 | 11→13 | 2544–2880 | 336 | **362** | trim 25 | **cut** | BAND_CATS_HALL_STAND (locked) |
| 12 | 13→14 | 2880–3144 | 264 | **362** | trim 97 | roll | BAND_CATS_STAGE_STAND (locked) |
| 13 | 14→15 | 3144–3504 | 360 | **362** | trim 1 | roll | BAND_CATS_STAGE_STAND (locked) |
| 14 | 15→16 | 3504–3672 | 168 | **243** | trim 74 | **cut** | BAND_CATS_STAGE_STAND (locked) |
| 15 | 16→17 | 3672–3960 | 288 | **362** | trim 73 | **cut** | SLOTH_FIRE_STAND (locked) |
| 16 | 17→18 | 3960–4272 | 312 | **362** | trim 49 | **cut** | BAND_CATS_STAGE_STAND (locked) |
| 17 | 18→19 | 4272–4560 | 288 | **362** | trim 73 | roll | SLOTH_GREEN_ROOM_STAND (locked) |
| 18 | 19→20 | 4560–4800 | 240 | **243** | trim 2 | **cut** | SLOTH_GREEN_ROOM_STAND (locked) |
| 19 | 20→21 | 4800–5076 | 276 | **243** | hold 34 (wav end) | **cut** | GREEN_ROOM_EMPTY (locked) |

Audio windows run `start_frame / 24` for `nframes / 24` seconds — window 1 is
0.000–15.083s, window 19 is 200.000–210.125s — sliced from the real wav, never
past 211.479979s.

Smash cut: row 12, 115.0s, frame 2760, inside window 11.

Eighteen of nineteen windows are pinned to a single plate, which is the whole
point: the shot cannot drift off a frame it is required to end on. The 34-frame
tail on window 19 holds STAGE_EMPTY — the catalog's "empty green room, then
empty stage" ending, delivered by the hold rather than by a generated morph.

## The catch: none of the performer injects exist yet

`plan.example.json` reports `ready: false` and lists **9 stills to shoot**. This
is the point, not an oversight. Behem has identity sheets (`01`/`02`/`03`/`06`,
all close-ups) and empty location plates (`04`/`05`/`07`/`08`). It has no
standing full-body composites, and CUs are identity refs only — feeding a bust
back in as a cut frame is what produced the legless band in the first place.

Every needed still carries a `brief` in `edl.json`: full-bleed 1344×768, the
locked portrait composited into the empty plate, whole body in frame, feet on
the floor, floor and shadow visible. Shoot those nine and the plan turns
`ready`.

One consequence worth stating out loud: the catalog's lyric shots want tight
close-ups, but a window's boundaries must be standing wides. The CU framing has
to come from inside the window (the prompt) or from smash-cut still inserts —
it can no longer come from the boundary frames.

## Verify before trusting

- `model.diffusion` is `minimax_h3_fl2va_pruned_fp8_scaled.safetensors`, read off
  the stock Comfy FL2VA graph. The current MCGrinder worker loads the *ref2va*
  checkpoint. Whether `MiniMaxH3SeamToVideo` + the merge patch behave the same on
  the fl2va checkpoint under the turbo LoRA is **unverified** — check on Behem
  before a full grind.
- FBC is off in the emitted graphs. Its 0.25/start-2 tuning was measured on
  20-step schedules; at 8 steps it is untested.
- Row 3 (22.0s, first lyric in) is `certain: false`. Force-align it from the wav
  before locking picture.
