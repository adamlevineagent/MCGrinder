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
