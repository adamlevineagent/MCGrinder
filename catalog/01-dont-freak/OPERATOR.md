# Don't Freak — operator notes (Behem)

Machine: **Behem** (Windows). ComfyUI **v0.30.0** at `C:\ComfyUI`.
Copy `config.behem.example.json` → repo-root `config.json` (gitignored).

This pack is a scaffold. Do **not** start a full-song grind from it. Hone first.

## What lives on Behem (not in git)

Identity stills and empty location plates:

```
C:\Users\adaml\dont-freak-refs\01-singer-guitarist.png
C:\Users\adaml\dont-freak-refs\02-drummer.png
C:\Users\adaml\dont-freak-refs\03-bassist.png
C:\Users\adaml\dont-freak-refs\04-green-room.png
C:\Users\adaml\dont-freak-refs\05-service-hall.png
C:\Users\adaml\dont-freak-refs\06-cat-violins.png   ← recast: gowned pair (not the retired unclothed standing-cats still)
C:\Users\adaml\dont-freak-refs\07-unplugged-stage.png
C:\Users\adaml\dont-freak-refs\08-apartment-fire.png
```

`02-drummer.png` is the implied name between `01` and `03`. If the file on disk
differs, junction/copy under that Comfy input name anyway and note it here.

Audio (~211s, ~92.3 BPM):

```
C:\Project Growth\THE PLAYFUL UNiVERSE\songs-2026-08-20-part1\Don't Freak\Don't Freak.wav
```

Canon lyrics were copied into this pack from Behem
`C:\Maestro\app\outputs\_director_assets\cebf215b\CANON_LYRICS.txt`.
The pack does not depend on that Maestro path.

## Wire stills into Comfy input

Junction or copy the refs folder so LoadImage sees pack `comfy_input` names:

```
mklink /J C:\ComfyUI\input\dont_freak C:\Users\adaml\dont-freak-refs
```

Then `dont_freak/01-singer-guitarist.png` resolves. Frames the worker writes go
to `C:\ComfyUI\input\dont_freak_frames` (create that folder).

Do not check the png/wav into git. `.gitignore` already drops `*.png` / `*.wav`.

## Frame EDL (edl.json) — the FL2VA window path

`edl.json` is the cut sheet: 21 rows at exact frames, riding the same 20-shot
timeline as `project.json` (each row carries the shot id whose `start_s` it must
equal). `plan_windows.py` turns it into 19 FL2VA windows plus 1 smash cut. See
[`docs/EDL.md`](../../docs/EDL.md).

```
python pipeline/plan_windows.py catalog/01-dont-freak --out catalog/01-dont-freak/plan.json
python pipeline/plan_windows.py catalog/01-dont-freak --wav "C:\Project Growth\THE PLAYFUL UNiVERSE\songs-2026-08-20-part1\Don't Freak\Don't Freak.wav"
python pipeline/plan_windows.py catalog/01-dont-freak --audio-input "dont_freak/Don't Freak.wav" --emit-graph C:\tmp\dont_freak_graphs
```

`plan.example.json` is the checked-in reference plan; `plan.json` is gitignored
like `state.json`.

### Nine inject stills to shoot first

The plan reports `ready: false` on purpose. Behem has identity CUs
(`01`/`02`/`03`/`06`) and empty plates (`04`/`05`/`07`/`08`) — it has no standing
full-body composites, and a CU used as a cut frame is what produced the legless
band. Each of these needs a full-bleed 1344x768 still, locked portrait
composited into the empty plate, whole body in frame, **both feet on the floor**,
floor and shadow visible. Briefs are in `edl.json` under `stills[]`.

```
C:\Users\adaml\dont-freak-refs\inject-01-claws-cu.png                  (claws on the neck; no face, no torso)
C:\Users\adaml\dont-freak-refs\inject-02-sloth-standing-stage.png
C:\Users\adaml\dont-freak-refs\inject-03-band-standing-stage.png
C:\Users\adaml\dont-freak-refs\inject-04-sloth-standing-fire.png
C:\Users\adaml\dont-freak-refs\inject-05-sloth-standing-hall.png
C:\Users\adaml\dont-freak-refs\inject-06-cats-standing-stage.png       (pair, gowns, never one cat)
C:\Users\adaml\dont-freak-refs\inject-07-band-cats-standing-stage.png
C:\Users\adaml\dont-freak-refs\inject-08-band-cats-standing-hall.png
C:\Users\adaml\dont-freak-refs\inject-09-sloth-standing-green-room.png
```

The existing junction already exposes them as `dont_freak/inject-NN-....png`.
Never use `00-band-bible-from-portraits.png` as a first frame, a last frame or a
layout — the EDL lists it as `role: forbidden` and a test enforces it.

### Wav into Comfy input (for SongWindow)

`SongWindow` crops the real track inside the graph, and `LoadAudio` only sees
`ComfyUI\input\`. Copy the master wav in once — no re-encode, no click track:

```
copy "C:\Project Growth\THE PLAYFUL UNiVERSE\songs-2026-08-20-part1\Don't Freak\Don't Freak.wav" C:\Users\adaml\dont-freak-refs\
```

It then resolves as `dont_freak/Don't Freak.wav`, which is the `--audio-input`
value above.

### Node pack: a NEW folder, beside the live kit

```
xcopy /E /I comfy_nodes\h3_edl_window C:\ComfyUI\custom_nodes\h3_edl_window
```

`C:\ComfyUI\custom_nodes\h3_seam_kit\` is not touched, not overwritten, not
synced. The new pack registers `H3EDLWindow` / `H3EDLStill` / `H3EDLSeamCheck`,
none of which collide with the kit's node names.

## GitHub `h3_seam_kit/` is not the live install

Do not "sync" or overwrite `C:\ComfyUI\custom_nodes\h3_seam_kit` from this repo.
Hunch (verify later; do not treat as fact): the GitHub node kit may be behind
the live kit plus MiniMax H3 Director, Sol-Attn, FirstBlockCache, and Spectrum.
A later PR can diff them. This pack does not touch nodes or Comfy patches.

## Hone that already succeeded (do not reroll identity)

- 5.167s sloth + **empty** green room
- `prompt_id` `1d8bd592-7ae2-4cb3-bfa9-3a54e5901110`
- 1344×768, Sol-Attn tau 1.3 + FBC 0.25, 20 steps (turbo LoRA is not on disk)
- ~140s wall
- Extra planet-toys appeared on the flight case — prompts now say the room is
  empty of extra props

Reproduce look-dev with `hone_batch.example.json`. Do not add a full-song fire
button. After hone, `from_pack.py` → copy beats → `snap_beats.py` → `run_chunk.py`.

## Pipeline sequence (no skip-hone button)

```
python pipeline/from_pack.py catalog/01-dont-freak --out catalog/01-dont-freak/state.json
# on Behem: build beats.json from the wav (librosa onset), then:
python pipeline/snap_beats.py
python pipeline/hone.py catalog/01-dont-freak/hone_batch.example.json
# only after hone is locked:
python pipeline/run_chunk.py
python pipeline/stitch.py
# overlays after concat: lyrics.json SRT + IM on the fire-apartment laptop
```

Verse-1 lyric in-times are force-align placeholders (after intro, before 0:46).
Replace those `start`/`end` values from the wav before burning the SRT.
