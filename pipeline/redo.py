#!/usr/bin/env python
"""Queue one or more chunks for a redo. Usage:
    python redo.py 1          # redo chunk 1 in isolation
    python redo.py 1 --chain  # redo chunk 1 AND following chunks (seam chain)

Each redo bumps the chunk's seed offset so the re-render is a fresh take.
The worker picks up pending chunks on its next tick; then re-run stitch.py.

State path comes from config.json (`state_file`).
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from load_config import load_config, state_path  # noqa: E402


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    ids = []
    chain = False
    for a in argv:
        if a == "--chain":
            chain = True
        else:
            ids.append(int(a))
    if not ids:
        print("usage: python redo.py <chunk-id> [ids...] [--chain]", file=sys.stderr)
        return 2

    cfg = load_config()
    path = state_path(cfg)
    if not path.is_file():
        print(f"state file missing: {path}", file=sys.stderr)
        return 1

    s = json.loads(path.read_text(encoding="utf-8"))
    by_id = {c["id"]: c for c in s["chunks"]}

    targets = []
    for cid in ids:
        if cid not in by_id:
            print(f"chunk {cid}: no such chunk")
            return 1
        targets.append(cid)

    if chain:
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

    path.write_text(json.dumps(s, indent=1, ensure_ascii=False), encoding="utf-8")
    print("done — worker picks these up on the next tick; then run stitch.py to rebuild the video")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
