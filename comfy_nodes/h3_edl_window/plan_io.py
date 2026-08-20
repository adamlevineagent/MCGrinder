"""Plan access for the h3_edl_window nodes.

Deliberately pure stdlib: no torch, no comfy, no numpy. The node module imports
its heavy dependencies inside the node functions, so this file (and the package
`__init__`) load in a bare python for tests on a box with no GPU.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

# Same seed policy as pipeline/plan_windows.py and pipeline/run_chunk.py, so a
# take number means the same thing whether the graph is built here or there.
SEED_BASE = 1000
SEED_STRIDE = 977
TAKE_STRIDE = 7919


def seed_for(window_id, take=0) -> int:
    return SEED_BASE + int(window_id) * SEED_STRIDE + int(take) * TAKE_STRIDE


def load_plan(path) -> dict:
    path = Path(path)
    if path.is_dir():
        path = path / "plan.json"
    if not path.is_file():
        raise ValueError(f"plan not found: {path}")
    plan = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(plan, dict) or plan.get("plan_schema") != 1:
        raise ValueError(f"not a plan_schema 1 file: {path}")
    if not plan.get("windows"):
        raise ValueError(f"plan has no windows: {path}")
    return plan


def window_count(plan) -> int:
    return len(plan.get("windows") or [])


def window_by_id(plan, window_id) -> dict:
    for window in plan.get("windows") or []:
        if int(window.get("id", -1)) == int(window_id):
            return window
    ids = ", ".join(str(w.get("id")) for w in plan.get("windows") or [])
    raise ValueError(f"window {window_id} not in plan (have: {ids})")


def still_name(window, which="first") -> str:
    if which not in ("first", "last"):
        raise ValueError("which must be 'first' or 'last'")
    name = window.get(f"{which}_still")
    if not name:
        raise ValueError(
            f"window {window.get('id')} has no {which}_still — the EDL row it "
            "closes on has no inject still on disk yet"
        )
    return name


def resolve_still(name, input_dir=None) -> Path:
    """Plan stills are named the way ComfyUI's input dir sees them."""
    path = Path(name)
    if path.is_absolute():
        if not path.is_file():
            raise ValueError(f"still not found: {path}")
        return path
    if input_dir:
        candidate = Path(input_dir) / name
        if candidate.is_file():
            return candidate
        raise ValueError(f"still not found: {candidate}")
    raise ValueError(f"still {name!r} is relative and no input dir was given")


def sha256_file(path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 16), b""):
            digest.update(block)
    return digest.hexdigest()


def summary(plan, window) -> str:
    """One line an operator can read off the node without opening the JSON."""
    fit = []
    if window.get("trim_tail_frames"):
        fit.append(f"trim {window['trim_tail_frames']}f")
    if window.get("hold_tail_frames"):
        fit.append(f"hold {window['hold_tail_frames']}f")
    if window.get("smash_rows"):
        fit.append("smash rows " + ",".join(str(r) for r in window["smash_rows"]))
    return (
        f"w{window.get('id')}/{window_count(plan)} {window.get('name')} | "
        f"frames {window.get('start_frame')}-{window.get('end_frame')} "
        f"span {window.get('span_frames')} -> {window.get('nframes')} "
        f"({window.get('pin')}, camera {window.get('camera')})"
        + (" | " + ", ".join(fit) if fit else "")
    )
