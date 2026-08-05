#!/usr/bin/env python
"""Snap every chunk's [offset, duration] onto the song's beat grid so cuts land
on beats. Chunks stay contiguous (next starts where previous ends)."""
import bisect
import json

STATE = "D:/ComfyUI-setup/mv_pipeline/state.json"
BEATS = "D:/ComfyUI-setup/mv_pipeline/beats.json"
SONG_END = 264.1
MIN_S, MAX_S = 5.0, 15.0

s = json.loads(open(STATE, encoding="utf-8").read())
beats = json.loads(open(BEATS, encoding="utf-8").read())


def nearest_beat(t):
    i = bisect.bisect_left(beats, t)
    if i == 0:
        return beats[0]
    if i >= len(beats):
        return beats[-1]
    return beats[i] if (beats[i] - t) < (t - beats[i - 1]) else beats[i - 1]


def beat_after(t, min_s):
    target = t + min_s
    i = bisect.bisect_left(beats, target)
    return beats[i] if i < len(beats) else beats[-1]


def beat_before(t, max_s):
    target = t + max_s
    i = bisect.bisect_right(beats, target)
    return beats[i - 1]


cursor = 0.0
for c in s["chunks"]:
    orig_start = c["offset_s"]
    orig_end = c["offset_s"] + c["duration_s"]
    start = nearest_beat(cursor if cursor > 0 else orig_start)
    end_min = beat_after(start, MIN_S)
    end_max = beat_before(start, MAX_S)
    end = min(nearest_beat(orig_end), end_max)
    if end - start < MIN_S - 1e-6:
        end = end_min
    c["offset_s"] = round(start, 3)
    c["duration_s"] = round(end - start, 3)
    cursor = end

# let the outro ride to the final beat, capped at H3's 15s max
last = s["chunks"][-1]
last["duration_s"] = round(min(beats[-1], SONG_END) - last["offset_s"], 3)
if last["duration_s"] > MAX_S:
    last["duration_s"] = MAX_S

open(STATE, "w", encoding="utf-8").write(json.dumps(s, indent=1, ensure_ascii=False))
total = sum(c["duration_s"] for c in s["chunks"])
print(f"total video: {total:.1f}s of {SONG_END}s")
for c in s["chunks"]:
    print(f"  {c['id']:>2} {c['offset_s']:>7.2f} -> {c['offset_s']+c['duration_s']:>7.2f}  ({c['duration_s']:>5.2f}s)  {c['name'][:34]}")
