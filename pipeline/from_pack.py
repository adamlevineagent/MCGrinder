#!/usr/bin/env python
"""Materialize a pipeline state.json from a SCHEMA v1 project pack.

Usage:
  python from_pack.py catalog/01-dont-freak
  python from_pack.py catalog/01-dont-freak --out /tmp/state.json

Does not submit renders. Honing and the chunk worker stay separate.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from load_config import (  # noqa: E402
    load_config,
    pack_dir,
    resolve_path,
    state_path,
)


def load_project(pack: Path) -> dict:
    path = pack / "project.json" if pack.is_dir() else pack
    if not path.is_file():
        raise FileNotFoundError(f"project.json not found: {path}")
    project = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(project, dict):
        raise ValueError("project.json must be a JSON object")
    if project.get("project_schema") != 1:
        raise ValueError("project_schema must be 1")
    return project


def shot_duration(shots, index, song_end) -> float:
    start = float(shots[index]["start_s"])
    if index + 1 < len(shots):
        end = float(shots[index + 1]["start_s"])
    else:
        end = float(song_end)
    return round(end - start, 3)


def comfy_ref(entry, fallback_sheet) -> str:
    if not entry:
        return fallback_sheet
    return entry.get("comfy_input") or entry.get("sheet") or fallback_sheet


def index_by_id(items):
    return {item["id"]: item for item in items if isinstance(item, dict) and "id" in item}


def ref_lookup(characters, locations) -> dict:
    """Map CHAR/LOC ids and pack-relative sheets onto Comfy input names."""
    lookup = {}
    for item in list(characters.values()) + list(locations.values()):
        mapped = comfy_ref(item, item.get("id"))
        if item.get("id"):
            lookup[item["id"]] = mapped
        if item.get("sheet"):
            lookup[item["sheet"]] = mapped
        if item.get("comfy_input"):
            lookup[item["comfy_input"]] = item["comfy_input"]
    return lookup


def resolve_one(ref, lookup, characters, locations) -> str:
    if not isinstance(ref, str):
        return ref
    if ref in lookup:
        return lookup[ref]
    if ref.startswith("CHAR"):
        return comfy_ref(characters.get(ref) or {}, ref)
    if ref.startswith("LOC"):
        return comfy_ref(locations.get(ref) or {}, ref)
    return ref


def resolve_refs(shot, characters, locations) -> list:
    lookup = ref_lookup(characters, locations)
    explicit = shot.get("refs") or []
    if explicit:
        return [resolve_one(ref, lookup, characters, locations) for ref in explicit]
    out = []
    for loc_id in shot.get("locations") or []:
        out.append(resolve_one(loc_id, lookup, characters, locations))
    for char_id in shot.get("characters") or []:
        out.append(resolve_one(char_id, lookup, characters, locations))
    return out


def first_frame_value(shot, characters, locations) -> str:
    lookup = ref_lookup(characters, locations)
    if shot.get("first_frame_img"):
        return resolve_one(shot["first_frame_img"], lookup, characters, locations)
    if shot.get("seam") == "prev":
        return "prev_last"
    locs = shot.get("locations") or []
    if locs:
        return resolve_one(locs[0], lookup, characters, locations)
    refs = shot.get("refs") or []
    if refs:
        return resolve_one(refs[0], lookup, characters, locations)
    return "prev_last"


def shots_to_chunks(project: dict) -> list:
    shots = project.get("shots") or []
    if not shots:
        raise ValueError("project.json has no shots")
    song_end = float((project.get("song_duration_s") or shots[-1].get("start_s") or 0))
    characters = index_by_id(project.get("characters") or [])
    locations = index_by_id(project.get("locations") or [])
    chunks = []
    for i, shot in enumerate(shots):
        duration = shot.get("duration_s")
        if duration is None:
            duration = shot_duration(shots, i, song_end)
        chunk = {
            "id": shot.get("id", i + 1),
            "name": shot.get("name") or f"shot {i + 1}",
            "offset_s": round(float(shot["start_s"]), 3),
            "duration_s": round(float(duration), 3),
            "first_frame": first_frame_value(shot, characters, locations),
            "refs": resolve_refs(shot, characters, locations),
            "prompt": shot.get("prompt") or "",
            "audio_mode": shot.get("audio_mode") or project.get("settings", {}).get("audio_default") or "raw",
            "status": "pending",
            "output": None,
            "prompt_id": None,
            "errors": 0,
            "redo": 0,
        }
        if shot.get("prompt_override") is not None:
            chunk["prompt_override"] = shot["prompt_override"]
        if shot.get("pulse_type"):
            chunk["pulse_type"] = shot["pulse_type"]
        if shot.get("pulse_gain") is not None:
            chunk["pulse_gain"] = shot["pulse_gain"]
        chunks.append(chunk)
    return chunks


def project_to_state(project: dict, cfg=None) -> dict:
    cfg = load_config() if cfg is None else cfg
    settings = project.get("settings") or {}
    slug = project.get("slug") or "mv"
    comfy = cfg.get("comfy") or {}
    output_dir = (
        project.get("output_dir")
        or cfg.get("output_dir")
        or (f"{comfy['output_dir']}/video/{slug}" if comfy.get("output_dir") else None)
        or f"C:/ComfyUI/output/video/{slug}"
    )
    frames_dir = (
        project.get("frames_dir")
        or cfg.get("frames_dir")
        or f"C:/ComfyUI/input/{slug}_frames"
    )
    song = project.get("song_path") or cfg.get("song") or project.get("song")
    if isinstance(song, dict):
        song_path = song.get("path")
        duration = song.get("duration_s", project.get("song_duration_s"))
    else:
        song_path = song
        duration = project.get("song_duration_s")
    state = {
        "project": project.get("project"),
        "slug": slug,
        "song": {"path": song_path, "duration_s": duration, "bpm": project.get("bpm")},
        "style_block": project.get("style_block") or "",
        "output_dir": output_dir,
        "frames_dir": frames_dir,
        "width": settings.get("width", 1344),
        "height": settings.get("height", 768),
        "sol_attn": settings.get("sol_attn", True),
        "sol_tau": settings.get("tau", 1.3),
        "audio_mode_default": settings.get("audio_default") or cfg.get("audio_mode_default") or "pulse",
        "chunks": shots_to_chunks(project),
    }
    return state


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build state.json from a SCHEMA project pack")
    ap.add_argument("pack", nargs="?", help="Pack directory or project.json path")
    ap.add_argument("--out", help="Write state JSON here (default: config state_file or stdout)")
    ap.add_argument("--stdout", action="store_true", help="Print JSON instead of writing a file")
    args = ap.parse_args(argv)

    cfg = load_config()
    pack = Path(args.pack) if args.pack else pack_dir(cfg)
    if pack is None:
        print("pass a pack directory or set config.pack", file=sys.stderr)
        return 2
    if not pack.is_absolute():
        pack = resolve_path(pack)

    project = load_project(pack)
    state = project_to_state(project, cfg)
    text = json.dumps(state, indent=2, ensure_ascii=False) + "\n"

    if args.stdout:
        sys.stdout.write(text)
        return 0

    out = Path(args.out) if args.out else state_path(cfg)
    if args.out:
        out = resolve_path(args.out) if not Path(args.out).is_absolute() else Path(args.out)
    elif cfg.get("state_file"):
        out = state_path(cfg)
    else:
        out = pack / "state.json" if pack.is_dir() else pack.with_name("state.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"wrote {out} ({len(state['chunks'])} chunks, {state['song']['duration_s']}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
