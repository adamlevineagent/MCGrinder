# The Production Loop

MCGrinder is built to run unattended for days, grinding a song into a video,
then re-grinding the bad chunks until the cut is right.

## Heartbeat

`run_chunk.py` advances the plan one step per invocation and is idempotent, so
drive it from a cron job:

```
every 45m: cd pipeline && python run_chunk.py
```

Each tick does exactly one of:
- submit the next `pending` chunk (build seam frame + song window, POST the
  seam-kit workflow)
- poll a `rendering` chunk; on success, **trim it to its exact song window**,
  mark `done`, and immediately submit the next chunk (no dead ticks)
- detect a vanished job (server restart) and reset it to `pending`
- report `ALL CHUNKS DONE` → run `stitch.py`

The worker starts ComfyUI itself if it is down (detached, `--cache-classic`,
CORS enabled, log to `comfy_server.log`).

## Ship of Theseus (the redo loop)

1. Assemble: `stitch.py` → concat done chunks + mux the real song (sub-second
   audio pass; H3's internal audio drifts at seams, the real track is
   sample-accurate).
2. Review: flag the chunk numbers that aren't right. (`redo.py` accepts a
   list; `--chain` also re-renders the next chunk when the seam between them
   is a continuous shot.)
3. `python redo.py 3 --chain` — chunk 3 gets a **fresh seed take** (the redo
   counter bumps the seed), its seam frame re-pins from the previous chunk,
   and the next chunk's opening re-pins from the new ending.
4. Re-stitch. Old + new chunks mix freely — the assembler just concatenates
   whatever is `done`.

Redo notes land in the plan itself: `prompt_override`, `refs_override` and
`audio_mode` are per-chunk patches applied at render time, so a fix survives
restarts and re-renders.

## Honing (low-res iteration)

`hone.py` renders A/B test configs at 832×480 directly through the seam kit,
writes a report line per test (`hone_report.jsonl`), and leaves every render
in `output/video/hone/` for visual comparison.

Typical A/B axes:
- `audio_mode`: pulse vs raw (motion sync vs vocal presence)
- refs: panel on/off, character sheets on/off (composition vs identity)
- `pulse_type` / `pulse_gain`: how strongly motion follows the beat
- prompt clauses: anti-lip-sync, beat count, panel-authority wording

Hone first, lock the winning config into the chunk plan, then run production.

## Timing rules of thumb

- 832×480, 5s, 20 steps: ~2.7 s/step once the model is loaded
- 1344×768, 15s: ~2.9 s/step, plus ~10–20 min of model load/decode on slow
  disks — budget 30–60 min per chunk cold
- Trimming a chunk to its window: sub-second (libx264 veryfast)
- Real-song mux at stitch: sub-second (`-c:v copy` + aac)
