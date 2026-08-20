#!/usr/bin/env python
"""Snap every chunk's [offset, duration] onto the song's beat grid so cuts land
on beats. Chunks stay contiguous (next starts where previous ends).

Paths come from config.json (`state_file`, `beats_file`) or the pack state.
Song end is state.song.duration_s — not a hardcoded BUSY length.
"""
import bisect
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from load_config import beats_path, load_config, state_path  # noqa: E402

MIN_S, MAX_S = 5.0, 15.0


def nearest_beat(beats, t):
    i = bisect.bisect_left(beats, t)
    if i == 0:
        return beats[0]
    if i >= len(beats):
        return beats[-1]
    return beats[i] if (beats[i] - t) < (t - beats[i - 1]) else beats[i - 1]


def beat_after(beats, t, min_s):
    target = t + min_s
    i = bisect.bisect_left(beats, target)
    return beats[i] if i < len(beats) else beats[-1]


def beat_before(beats, t, max_s):
    target = t + max_s
    i = bisect.bisect_right(beats, target)
    return beats[i - 1]


def snap_state(s, beats, min_s=MIN_S, max_s=MAX_S):
    song_end = float((s.get("song") or {}).get("duration_s") or beats[-1])
    cursor = 0.0
    for c in s["chunks"]:
        orig_start = c["offset_s"]
        orig_end = c["offset_s"] + c["duration_s"]
        start = nearest_beat(beats, cursor if cursor > 0 else orig_start)
        end_min = beat_after(beats, start, min_s)
        end_max = beat_before(beats, start, max_s)
        end = min(nearest_beat(beats, orig_end), end_max)
        if end - start < min_s - 1e-6:
            end = end_min
        c["offset_s"] = round(start, 3)
        c["duration_s"] = round(end - start, 3)
        cursor = end

    last = s["chunks"][-1]
    last["duration_s"] = round(min(beats[-1], song_end) - last["offset_s"], 3)
    if last["duration_s"] > max_s:
        last["duration_s"] = max_s
    return song_end


def main():
    cfg = load_config()
    state_file = state_path(cfg)
    beats_file = beats_path(cfg)
    if not state_file.is_file():
        print(f"state file missing: {state_file}", file=sys.stderr)
        sys.exit(1)
    if not beats_file.is_file():
        print(f"beats file missing: {beats_file} — analyze the wav on the operator box first",
              file=sys.stderr)
        sys.exit(1)

    s = json.loads(state_file.read_text(encoding="utf-8"))
    beats = json.loads(beats_file.read_text(encoding="utf-8"))
    if not isinstance(beats, list) or not beats:
        print("beats.json must be a non-empty list of times", file=sys.stderr)
        sys.exit(1)

    song_end = snap_state(s, beats)
    state_file.write_text(json.dumps(s, indent=1, ensure_ascii=False), encoding="utf-8")
    total = sum(c["duration_s"] for c in s["chunks"])
    print(f"total video: {total:.1f}s of {song_end}s")
    for c in s["chunks"]:
        print(f"  {c['id']:>2} {c['offset_s']:>7.2f} -> {c['offset_s']+c['duration_s']:>7.2f}  "
              f"({c['duration_s']:>5.2f}s)  {c['name'][:34]}")


if __name__ == "__main__":
    main()
