#!/usr/bin/env python
"""Queue one or more chunks for a redo. Usage:
    python redo.py 1          # redo chunk 1 in isolation
    python redo.py 1 --chain  # redo chunk 1 AND chunk 2 (whose opening frame is
                              # pinned to chunk 1's last frame) — use when the
                              # seam between them is a continuous shot
Each redo bumps the chunk's seed offset so the re-render is a fresh take.
The worker picks up pending chunks on its next tick; then re-run stitch.py.
"""
import json
import sys

STATE = "D:/ComfyUI-setup/mv_pipeline/state.json"

ids = []
chain = False
for a in sys.argv[1:]:
    if a == "--chain":
        chain = True
    else:
        ids.append(int(a))

s = json.loads(open(STATE, encoding="utf-8").read())
by_id = {c["id"]: c for c in s["chunks"]}

targets = []
for cid in ids:
    if cid not in by_id:
        print(f"chunk {cid}: no such chunk")
        sys.exit(1)
    targets.append(cid)

if chain:
    # include each following chunk whose seam depends on a redone chunk,
    # stopping at the first hard-cut (page-turn) prompt boundary is complex —
    # so chain simply carries forward through consecutive ids
    nxt = max(targets) + 1
    while nxt in by_id:
        targets.append(nxt)
        nxt += 1

for cid in targets:
    c = by_id[cid]
    c["status"] = "pending"
    c["output"] = None
    c["prompt_id"] = None
    c["errors"] = 0
    c["redo"] = c.get("redo", 0) + 1
    print(f"  queued redo: chunk {cid} ({c['name']}) — fresh seed take #{c['redo']}")

open(STATE, "w", encoding="utf-8").write(json.dumps(s, indent=1, ensure_ascii=False))
print("done — worker picks these up on the next tick; then run stitch.py to rebuild the video")
