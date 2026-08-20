#!/usr/bin/env python
"""Turn a frame EDL into a queue of H3 FL2VA windows. No Comfy, no GPU.

The EDL owns the cut frames. Every picture change is a row at an exact frame;
every window's FIRST and LAST frame is one of those rows' inject stills, so the
edit cuts on frames we already own instead of hoping the model invents a cut.

A row's `transition` decides what the join is. `roll` ends the window on the
next row's still, so the two windows share a frame and the join is seamless.
`cut` ends the window on its OWN opening still, so a locked shot returns to
where it started and the picture change is a hard cut — which is what you want
whenever the next row is in a different room.

Usage:
  python pipeline/plan_windows.py catalog/01-dont-freak
  python pipeline/plan_windows.py catalog/01-dont-freak --stdout
  python pipeline/plan_windows.py catalog/01-dont-freak --fit under
  python pipeline/plan_windows.py catalog/01-dont-freak --wav "D:/Don't Freak.wav"
  python pipeline/plan_windows.py catalog/01-dont-freak --emit-graph /tmp/graphs

Emits jobs for the LIVE h3_seam_kit (MiniMaxH3SeamToVideo + SongWindow +
SeamFrame). It does not replace those nodes and does not submit anything.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from from_pack import index_by_id, load_project, resolve_refs  # noqa: E402
from load_config import load_config, resolve_path  # noqa: E402

FPS = 24
LATTICE = (124, 243, 362)
BOUNDARY_KINDS = ("inject", "hold", "end")
ROW_KINDS = ("inject", "hold", "smash", "end")
TRANSITIONS = ("roll", "cut")
INJECT_BODIES = ("standing_full", "empty_plate", "cu_object")
FIT_MODES = ("cover", "under", "nearest")
MAX_REFS = 4
SEED_BASE = 1000
SEED_STRIDE = 977
TAKE_STRIDE = 7919
SAMPLE_WIDTH_CODEC = {1: "pcm_u8", 2: "pcm_s16le", 3: "pcm_s24le", 4: "pcm_s32le"}

LOCKED_CAMERA_NOTE = (
    "Locked camera: the frame does not move. No push-in, no pull-back, no dolly, "
    "no orbit, no handheld drift. The first and last frames of this window are "
    "fixed plates and the camera stays exactly where they put it."
)
SAME_STILL_NOTE = (
    "The first and last frame of this window are the same plate: the shot ends "
    "exactly where it started."
)


def frame_for(t_sec, fps=FPS) -> int:
    """Frame index of a timestamp. round(), so 11.0s -> 264 at 24fps."""
    return int(round(float(t_sec) * float(fps)))


def probe_wav(path) -> dict:
    """Read the real wav header (stdlib, PCM only). Fills the EDL audio block."""
    with wave.open(str(path), "rb") as handle:
        sample_rate = handle.getframerate()
        channels = handle.getnchannels()
        sample_width = handle.getsampwidth()
        total_samples = handle.getnframes()
    duration = total_samples / float(sample_rate)
    return {
        "path": str(path),
        "codec": SAMPLE_WIDTH_CODEC.get(sample_width, f"pcm_{sample_width * 8}"),
        "sample_rate": sample_rate,
        "channels": channels,
        "duration_s": round(duration, 6),
        "total_samples": total_samples,
        "frames_24": frame_for(duration),
    }


def load_edl(path) -> dict:
    path = Path(path)
    path = path / "edl.json" if path.is_dir() else path
    if not path.is_file():
        raise FileNotFoundError(f"edl.json not found: {path}")
    edl = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(edl, dict):
        raise ValueError("edl.json must be a JSON object")
    if edl.get("edl_schema") != 1:
        raise ValueError("edl_schema must be 1")
    return edl


def still_index(edl) -> dict:
    return {s["id"]: s for s in edl.get("stills") or [] if isinstance(s, dict) and "id" in s}


def validate_edl(edl, project=None) -> list:
    """Everything that would silently produce a wrong cut or a legless bust."""
    problems = []
    fps = edl.get("fps", FPS)
    stills = still_index(edl)
    rows = edl.get("rows") or []
    if not rows:
        return ["edl has no rows"]

    audio = edl.get("audio") or {}
    duration = audio.get("duration_s")
    shots = {s.get("id"): s for s in ((project or {}).get("shots") or [])}

    prev_frame = None
    for row in rows:
        tag = f"row {row.get('id')} ({row.get('text')!r})"
        kind = row.get("kind")
        if kind not in ROW_KINDS:
            problems.append(f"{tag}: kind must be one of {ROW_KINDS}, got {kind!r}")
        if row.get("transition") not in (None,) + TRANSITIONS:
            problems.append(
                f"{tag}: transition must be one of {TRANSITIONS}, got {row['transition']!r}")
        want = frame_for(row.get("t_sec", 0), fps)
        if row.get("frame_24") != want:
            problems.append(
                f"{tag}: frame_24 {row.get('frame_24')} != round({row.get('t_sec')} * {fps}) = {want}"
            )
        if prev_frame is not None and row.get("frame_24", 0) <= prev_frame:
            problems.append(f"{tag}: frames must strictly increase (after {prev_frame})")
        prev_frame = row.get("frame_24", prev_frame)

        still = stills.get(row.get("still"))
        if still is None:
            problems.append(f"{tag}: unknown still {row.get('still')!r}")
        elif kind in BOUNDARY_KINDS or kind == "smash":
            if still.get("role") != "inject":
                problems.append(
                    f"{tag}: still {still['id']} has role {still.get('role')!r} — "
                    "identity sheets and collages are never cut frames"
                )
            elif still.get("body") not in INJECT_BODIES:
                problems.append(
                    f"{tag}: still {still['id']} body {still.get('body')!r} is not one of "
                    f"{INJECT_BODIES} — inject frames must stand on the floor or be a plate"
                )

        shot_id = row.get("shot")
        if shot_id is not None:
            shot = shots.get(shot_id) if shots else None
            if shots and shot is None:
                problems.append(f"{tag}: shot {shot_id} is not in the pack")
            elif shot is not None and abs(float(shot["start_s"]) - float(row["t_sec"])) > 1e-6:
                problems.append(
                    f"{tag}: t_sec {row['t_sec']} != pack shot {shot_id} start_s {shot['start_s']} — "
                    "the EDL must ride the catalog timeline, not a parallel one"
                )

    if rows[0].get("frame_24") != 0:
        problems.append("first row must sit on frame 0")
    if rows[-1].get("kind") != "end":
        problems.append("last row must have kind 'end'")
    if sum(1 for r in rows if r.get("kind") == "end") != 1:
        problems.append("exactly one row may have kind 'end'")
    if duration is not None and abs(float(rows[-1].get("t_sec", 0)) - float(duration)) > 1e-6:
        problems.append(
            f"end row t_sec {rows[-1].get('t_sec')} != audio duration_s {duration}"
        )
    if duration is not None and audio.get("frames_24") != frame_for(duration, fps):
        problems.append("audio.frames_24 does not match round(duration_s * fps)")

    rules = (project or {}).get("cast_rules") or {}
    cats_from = rules.get("cats_from_s")
    if cats_from is not None:
        for row in rows:
            still = stills.get(row.get("still")) or {}
            label = f"{still.get('id', '')} {still.get('name', '')}".lower()
            if re.search(r"\bcats?\b", label.replace("_", " ").replace("-", " ")):
                if float(row.get("t_sec", 0)) < float(cats_from):
                    problems.append(
                        f"row {row.get('id')}: cats at {row.get('t_sec')}s, never before {cats_from}s"
                    )
    return problems


def choose_length(span, mode="cover", max_frames=None):
    """Pick a lattice length for a span of `span` frames between two injects.

    A window of n frames supplies n-1 NEW frames plus the boundary frame it
    shares with the next window, so the fit is measured against n-1.
      cover   -> smallest lattice that reaches the next inject (trim the tail)
      under   -> largest lattice that stays inside it (hold the still)
      nearest -> whichever residual is smallest
    Returns (nframes, clamped) where clamped means the wav ran out first.
    """
    opts = [n for n in LATTICE if max_frames is None or n <= max_frames]
    clamped = len(opts) < len(LATTICE)
    if not opts:
        opts = [LATTICE[0]]
        clamped = True
    if mode == "cover":
        fits = [n for n in opts if n - 1 >= span]
        return (min(fits) if fits else max(opts)), clamped
    if mode == "under":
        fits = [n for n in opts if n - 1 <= span]
        return (max(fits) if fits else min(opts)), clamped
    return min(opts, key=lambda n: (abs((n - 1) - span), n)), clamped


def pack_boundaries(rows, min_fill):
    """Walk the boundary rows and pair them into windows.

    A boundary closer than min_fill to the open window's start cannot begin an
    H3 window (the shortest clip is 124 frames), so it is demoted to a smash:
    an editorial still cut in over the window that spans it. `hold` rows are
    never demoted — tagging a span as a hold is what authorises skipping an
    intermediate smash.
    """
    bounds = [r for r in rows if r.get("kind") in BOUNDARY_KINDS]
    pairs, demoted = [], []
    if len(bounds) < 2:
        return pairs, demoted
    i = 0
    while i < len(bounds) - 1:
        j = i + 1
        while (j < len(bounds) - 1
               and bounds[j]["frame_24"] - bounds[i]["frame_24"] < min_fill
               and bounds[j].get("kind") != "hold"):
            demoted.append(bounds[j])
            j += 1
        pairs.append((bounds[i], bounds[j]))
        i = j
    # A short FINAL span has nothing to merge forward into: merge it backwards.
    while len(pairs) > 1:
        opened, closed = pairs[-1]
        if closed["frame_24"] - opened["frame_24"] >= min_fill or opened.get("kind") == "hold":
            break
        demoted.append(opened)
        pairs.pop()
        prev_open, _ = pairs.pop()
        pairs.append((prev_open, closed))
    return pairs, demoted


def seed_for(window_id, take=0) -> int:
    """Same policy as run_chunk.py, so a redo is a fresh take of one window."""
    return SEED_BASE + window_id * SEED_STRIDE + take * TAKE_STRIDE


def _prompt_parts(shot, camera, same_still, style_block):
    parts = [(shot or {}).get("prompt") or ""]
    parts.append(LOCKED_CAMERA_NOTE if camera == "locked"
                 else f"Camera move: {camera}. Start on the first pinned frame and finish on "
                      "the last pinned frame; make no other camera move.")
    if same_still:
        parts.append(SAME_STILL_NOTE)
    if style_block:
        parts.append(style_block)
    return " ".join(p.strip() for p in parts if p and p.strip())


def plan_from_edl(edl, project, fit=None, audio_input=None, take=0) -> dict:
    """EDL rows -> a queue of FL2VA window jobs."""
    fps = edl.get("fps", FPS)
    defaults = edl.get("defaults") or {}
    fit = fit or defaults.get("fit") or "cover"
    if fit not in FIT_MODES:
        raise ValueError(f"fit must be one of {FIT_MODES}")
    min_fill = int(defaults.get("min_fill_frames") or LATTICE[0])
    audio = edl.get("audio") or {}
    video = edl.get("video") or {}
    model = edl.get("model") or {}
    settings = (project or {}).get("settings") or {}
    stills = still_index(edl)
    rows = edl.get("rows") or []
    shots = {s.get("id"): s for s in ((project or {}).get("shots") or [])}
    characters = index_by_id((project or {}).get("characters") or [])
    locations = index_by_id((project or {}).get("locations") or [])
    sample_rate = int(audio.get("sample_rate") or 48000)
    total_samples = audio.get("total_samples")
    song_end_s = float(audio.get("duration_s") or 0.0)
    width = int(video.get("width") or settings.get("width") or 1344)
    height = int(video.get("height") or settings.get("height") or 768)
    style_block = (project or {}).get("style_block") or ""

    pairs, demoted = pack_boundaries(rows, min_fill)
    demoted_ids = {r["id"] for r in demoted}
    warnings = []

    windows = []
    for index, (open_row, close_row) in enumerate(pairs, start=1):
        start_frame = open_row["frame_24"]
        end_frame = close_row["frame_24"]
        span = end_frame - start_frame
        start_s = start_frame / float(fps)
        room = int((song_end_s - start_s) * fps) if song_end_s else None
        row_fit = open_row.get("fit") or fit
        nframes, clamped = choose_length(span, row_fit, room)
        residual = (nframes - 1) - span

        # A window rolls onto the next one's opening still only when the join is
        # seamless. A `cut` join ends the window on its OWN opening still, so a
        # locked shot returns to where it started and the picture change at the
        # next row is a hard cut instead of a 10-second morph between rooms.
        transition = close_row.get("transition") or defaults.get("transition") or "roll"
        first = stills.get(open_row.get("still")) or {}
        last = stills.get((close_row if transition == "roll" else open_row).get("still")) or {}
        incoming = stills.get(close_row.get("still")) or {}
        shot = shots.get(open_row.get("shot")) or {}
        refs = resolve_refs(shot, characters, locations) if shot else []
        if len(refs) > MAX_REFS:
            warnings.append(
                f"window {index}: shot {shot.get('id')} has {len(refs)} refs, "
                f"MiniMaxH3SeamToVideo takes {MAX_REFS} — dropped the tail"
            )
            refs = refs[:MAX_REFS]
        same_still = bool(first.get("id")) and first.get("id") == last.get("id")
        duration_s = nframes / float(fps)
        end_sample = int(round((start_frame + nframes) * sample_rate / float(fps)))
        if total_samples:
            end_sample = min(end_sample, int(total_samples))

        window = {
            "id": index,
            "name": f"{open_row.get('text')} -> {close_row.get('text')}",
            "shot": open_row.get("shot"),
            "from_row": open_row.get("id"),
            "to_row": close_row.get("id"),
            "start_frame": start_frame,
            "end_frame": end_frame,
            "span_frames": span,
            "nframes": nframes,
            "trim_tail_frames": max(0, residual),
            "hold_tail_frames": max(0, -residual),
            "clamped_by_song_end": bool(clamped),
            "fit": row_fit,
            "out_transition": transition,
            "pin": "same_still" if same_still else "cross",
            "first_still_id": first.get("id"),
            "last_still_id": last.get("id"),
            "first_still": first.get("comfy_input"),
            "last_still": last.get("comfy_input"),
            "first_still_status": first.get("status"),
            "last_still_status": last.get("status"),
            "hold_still_id": incoming.get("id") if residual < 0 else None,
            "hold_still": incoming.get("comfy_input") if residual < 0 else None,
            "camera": open_row.get("camera") or defaults.get("camera") or "locked",
            "audio_mode": open_row.get("audio_mode") or defaults.get("audio_mode") or "raw",
            "audio_start_s": round(start_s, 6),
            "audio_end_s": round(start_s + duration_s, 6),
            "duration_s": round(duration_s, 6),
            "audio_start_sample": int(round(start_frame * sample_rate / float(fps))),
            "audio_end_sample": end_sample,
            "seed": seed_for(index, take),
            "take": take,
            "steps": int(model.get("steps") or 8),
            "turbo_lora": model.get("turbo_lora"),
            "lora_strength": float(model.get("lora_strength") or 1.0),
            "width": width,
            "height": height,
            "refs": refs,
            "prompt": (shot or {}).get("prompt") or "",
            "smash_rows": [],
            "status": "pending",
        }
        window["prompt_full"] = _prompt_parts(shot, window["camera"], same_still, style_block)
        if span < min_fill:
            warnings.append(
                f"window {index}: span {span}f is under the {min_fill}f floor and could not be "
                "demoted (hold row) — it trims hard"
            )
        if residual < 0 and row_fit == "cover" and not clamped:
            warnings.append(
                f"window {index}: span {span}f is longer than the {max(LATTICE)}-frame lattice, "
                f"so the tail holds for {-residual}f — split it with another inject"
            )
        if window["camera"] == "locked" and not same_still:
            warnings.append(
                f"window {index}: camera is locked but it is pinned between "
                f"{first.get('id')} and {last.get('id')} — a locked frame cannot get from "
                "one to the other. Name the move, or make the closing row a cut"
            )
        if song_end_s and window["audio_end_s"] > song_end_s + 1e-9:
            warnings.append(
                f"window {index}: audio window ends at {window['audio_end_s']}s, past the "
                f"{song_end_s}s wav"
            )
        windows.append(window)

    smash_cuts = []
    for row in rows:
        if row.get("kind") != "smash" and row.get("id") not in demoted_ids:
            continue
        still = stills.get(row.get("still")) or {}
        host = next((w for w in windows
                     if w["start_frame"] < row["frame_24"] < w["end_frame"]), None)
        smash = {
            "row": row.get("id"),
            "text": row.get("text"),
            "t_sec": row.get("t_sec"),
            "frame_24": row.get("frame_24"),
            "still_id": still.get("id"),
            "still": still.get("comfy_input"),
            "shot": row.get("shot"),
            "inside_window": host["id"] if host else None,
            "auto_demoted": row.get("id") in demoted_ids,
        }
        if host is None:
            warnings.append(f"smash row {row.get('id')} at frame {row.get('frame_24')} "
                            "does not sit inside any window")
        smash_cuts.append(smash)

    needed = {}
    for window in windows:
        for key in ("first", "last", "hold"):
            still = stills.get(window[f"{key}_still_id"]) or {}
            if still and still.get("status") != "on_behem":
                entry = needed.setdefault(still["id"], {
                    "id": still["id"],
                    "name": still.get("name"),
                    "status": still.get("status"),
                    "body": still.get("body"),
                    "comfy_input": still.get("comfy_input"),
                    "behem": still.get("behem"),
                    "brief": still.get("brief"),
                    "windows": [],
                })
                if window["id"] not in entry["windows"]:
                    entry["windows"].append(window["id"])

    uncertain = [{"row": r["id"], "text": r.get("text"), "t_sec": r.get("t_sec"),
                  "notes": r.get("notes")}
                 for r in rows if r.get("certain") is False]

    timeline_frames = rows[-1]["frame_24"] - rows[0]["frame_24"] if rows else 0
    generated = sum(w["nframes"] for w in windows)
    plan = {
        "plan_schema": 1,
        "project": edl.get("project"),
        "slug": edl.get("slug"),
        "fps": fps,
        "fit": fit,
        "generated_from": {
            "edl": f"{edl.get('pack')}/edl.json" if edl.get("pack") else "edl.json",
            "pack": edl.get("pack"),
            "planner": "pipeline/plan_windows.py",
        },
        "consumes": {
            "conditioning": "MiniMaxH3SeamToVideo (live h3_seam_kit) — first_frame + last_frame pinned",
            "audio": "SongWindow (live h3_seam_kit) — offset_s / duration_s below, raw wav, no click",
            "seam": "SeamFrame (live h3_seam_kit) — only needed to audit a rendered window's last frame",
            "note": "This plan drives the installed kit. It does not replace or vendor it.",
        },
        "video": {"width": 1344, "height": 768, "lattice": list(LATTICE)},
        "audio": dict(audio),
        "model": dict(model),
        "audio_input": audio_input or (edl.get("defaults") or {}).get("audio_input"),
        "style_block": style_block,
        "totals": {
            "windows": len(windows),
            "smash_cuts": len(smash_cuts),
            "timeline_frames": timeline_frames,
            "timeline_s": round(timeline_frames / float(fps), 6),
            "generated_frames": generated,
            "trim_frames": sum(w["trim_tail_frames"] for w in windows),
            "hold_frames": sum(w["hold_tail_frames"] for w in windows),
            "overhead_frames": generated - timeline_frames,
            "overhead_pct": round(100.0 * (generated - timeline_frames) / timeline_frames, 2)
            if timeline_frames else 0.0,
            "by_length": {str(n): sum(1 for w in windows if w["nframes"] == n) for n in LATTICE},
        },
        "needed_stills": sorted(needed.values(), key=lambda s: s["id"]),
        "uncertain_rows": uncertain,
        "smash_cuts": smash_cuts,
        "warnings": warnings,
        "windows": windows,
    }
    by_id = {window["id"]: window for window in windows}
    for smash in smash_cuts:
        if smash["inside_window"]:
            by_id[smash["inside_window"]]["smash_rows"].append(smash["row"])
    plan["ready"] = not plan["needed_stills"] and not warnings
    return plan


def build_window_graph(plan, window, sol_attn=True, fbc=False, diffusion=None) -> dict:
    """ComfyUI API-format graph for one window, wired to the LIVE kit nodes.

    UNET -> turbo LoRA -> (Sol-Attn) -> SigmaShift -> (FBC) -> guider/scheduler,
    with MiniMaxH3SeamToVideo taking the two inject stills as pinned first/last
    frames and SongWindow cropping the real wav to this window.
    """
    model_cfg = plan.get("model") or {}
    audio_input = plan.get("audio_input")
    if not audio_input:
        raise ValueError("plan.audio_input is unset — pass --audio-input (the master wav "
                         "as ComfyUI sees it under input/)")
    for key in ("first_still", "last_still"):
        if not window.get(key):
            raise ValueError(f"window {window['id']}: {key} has no comfy_input name")

    nodes = {
        "1": {"class_type": "UNETLoader", "inputs": {
            "unet_name": diffusion or model_cfg.get("diffusion"), "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {
            "clip_name": "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors", "type": "minimax"}},
        "3": {"class_type": "VAELoader", "inputs": {
            "vae_name": "minimax_h3_video_vae_fp16.safetensors"}},
        "4": {"class_type": "VAELoader", "inputs": {
            "vae_name": "minimax_h3_audio_vae_fp32.safetensors"}},
        "5": {"class_type": "LoraLoaderModelOnly", "inputs": {
            "model": ["1", 0], "lora_name": model_cfg.get("turbo_lora"),
            "strength_model": float(window.get("lora_strength", 1.0))}},
    }
    tail = "5"
    if sol_attn:
        nodes["6"] = {"class_type": "SolAttnPatch", "inputs": {
            "model": [tail, 0], "tau": 1.3, "start_percent": 0.2, "end_percent": 0.9,
            "min_tokens": 4096, "int8_qk": True, "sink_conditioning": "exact_kv",
            "morton": False, "morton_curve": "2d_frame", "int8_pv": True,
            "verbose": False, "use_tma": False, "dense_blocks": ""}}
        tail = "6"
    nodes["7"] = {"class_type": "MiniMaxH3SigmaShift", "inputs": {
        "model": [tail, 0],
        "shift_video": float(model_cfg.get("shift_video") or 12.0),
        "shift_audio": float(model_cfg.get("shift_audio") or 3.0)}}
    tail = "7"
    if fbc:
        nodes["8"] = {"class_type": "H3FirstBlockCache", "inputs": {
            "model": [tail, 0], "threshold": 0.25, "start_step": 2,
            "end_dense_steps": 2, "max_consecutive_skips": 2}}
        tail = "8"

    nodes["10"] = {"class_type": "LoadImage", "inputs": {"image": window["first_still"]}}
    nodes["11"] = {"class_type": "LoadImage", "inputs": {"image": window["last_still"]}}
    nodes["12"] = {"class_type": "LoadAudio", "inputs": {"audio": audio_input}}
    nodes["13"] = {"class_type": "SongWindow", "inputs": {
        "audio": ["12", 0],
        "offset_s": window["audio_start_s"],
        "duration_s": window["duration_s"]}}

    seam_inputs = {
        "clip": ["2", 0], "vae": ["3", 0], "audio_vae": ["4", 0],
        "prompt": window["prompt_full"],
        "width": window["width"], "height": window["height"],
        "length": window["nframes"],
        "ref_image_size": "match",
        "first_frame": ["10", 0],
        "last_frame": ["11", 0],
        "ref_audio_1": ["13", 0],
    }
    node_id = 30
    for i, ref in enumerate(window.get("refs") or [], start=1):
        nodes[str(node_id)] = {"class_type": "LoadImage", "inputs": {"image": ref}}
        seam_inputs[f"ref_image_{i}"] = [str(node_id), 0]
        node_id += 1
    nodes["14"] = {"class_type": "MiniMaxH3SeamToVideo", "inputs": seam_inputs}

    nodes["20"] = {"class_type": "RandomNoise", "inputs": {"noise_seed": window["seed"]}}
    nodes["21"] = {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "res_multistep"}}
    nodes["22"] = {"class_type": "BasicScheduler", "inputs": {
        "model": [tail, 0], "scheduler": "simple",
        "steps": window["steps"], "denoise": 1.0}}
    nodes["23"] = {"class_type": "BasicGuider", "inputs": {
        "model": [tail, 0], "conditioning": ["14", 0]}}
    nodes["24"] = {"class_type": "SamplerCustomAdvanced", "inputs": {
        "noise": ["20", 0], "guider": ["23", 0], "sampler": ["21", 0],
        "sigmas": ["22", 0], "latent_image": ["14", 1]}}
    nodes["25"] = {"class_type": "VAEDecode", "inputs": {"samples": ["24", 0], "vae": ["3", 0]}}
    nodes["26"] = {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["24", 0], "vae": ["4", 0]}}
    nodes["27"] = {"class_type": "CreateVideo", "inputs": {
        "images": ["25", 0], "fps": plan.get("fps", FPS), "audio": ["26", 0], "bit_depth": 8}}
    nodes["28"] = {"class_type": "SaveVideo", "inputs": {
        "video": ["27", 0],
        "filename_prefix": f"video/{plan.get('slug') or 'mv'}/w{window['id']:02d}",
        "format": "auto", "codec": "auto"}}
    return nodes


def summarize(plan) -> str:
    totals = plan["totals"]
    lines = [
        f"{plan['project']}: {totals['windows']} windows, {totals['smash_cuts']} smash cuts, "
        f"{totals['timeline_frames']} timeline frames ({totals['timeline_s']}s)",
        "  lengths: " + ", ".join(f"{n}x{c}" for n, c in totals["by_length"].items() if c),
        f"  generated {totals['generated_frames']}f, trim {totals['trim_frames']}f, "
        f"hold {totals['hold_frames']}f, overhead {totals['overhead_pct']}%",
    ]
    if plan["needed_stills"]:
        lines.append(f"  NOT READY: {len(plan['needed_stills'])} inject stills to shoot: "
                     + ", ".join(s["id"] for s in plan["needed_stills"]))
    for note in plan["warnings"]:
        lines.append(f"  warn: {note}")
    for row in plan["uncertain_rows"]:
        lines.append(f"  uncertain: row {row['row']} at {row['t_sec']}s ({row['text']})")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Plan H3 FL2VA windows from a frame EDL")
    ap.add_argument("pack", nargs="?", help="Pack directory (with edl.json + project.json)")
    ap.add_argument("--edl", help="EDL path (default: <pack>/edl.json)")
    ap.add_argument("--out", help="Write the plan here (default: <pack>/plan.json)")
    ap.add_argument("--stdout", action="store_true", help="Print the plan instead of writing it")
    ap.add_argument("--fit", choices=FIT_MODES, help="Window fit policy (default: EDL default)")
    ap.add_argument("--wav", help="Probe this wav and stamp the exact audio numbers")
    ap.add_argument("--audio-input", help="Master wav as ComfyUI sees it under input/")
    ap.add_argument("--emit-graph", help="Also write one ComfyUI API graph per window here")
    ap.add_argument("--take", type=int, default=0, help="Take number (reseeds every window)")
    ap.add_argument("--strict", action="store_true", help="Exit non-zero on any warning")
    args = ap.parse_args(argv)

    cfg = load_config()
    pack = Path(args.pack) if args.pack else resolve_path(cfg.get("pack"))
    if pack is None and not args.edl:
        print("pass a pack directory or set config.pack", file=sys.stderr)
        return 2
    if pack is not None and not pack.is_absolute():
        pack = resolve_path(pack)

    edl = load_edl(args.edl or pack)
    project = {}
    if pack is not None:
        project_path = pack / "project.json" if pack.is_dir() else pack
        if project_path.is_file():
            project = load_project(project_path)

    if args.wav:
        try:
            probed = probe_wav(args.wav)
        except (wave.Error, EOFError, OSError) as exc:
            print(f"  could not probe {args.wav}: {exc} (stdlib wave reads PCM only)",
                  file=sys.stderr)
            return 2
        before = dict(edl.get("audio") or {})
        edl.setdefault("audio", {}).update(probed)
        end_row = edl["rows"][-1]
        if abs(float(end_row["t_sec"]) - probed["duration_s"]) > 1e-6:
            print(f"  wav probe moved the end row: {end_row['t_sec']}s -> {probed['duration_s']}s "
                  f"(frame {end_row['frame_24']} -> {probed['frames_24']})")
            end_row["t_sec"] = probed["duration_s"]
            end_row["frame_24"] = probed["frames_24"]
        if before.get("sample_rate") not in (None, probed["sample_rate"]):
            print(f"  wav probe changed sample_rate: {before.get('sample_rate')} -> "
                  f"{probed['sample_rate']}")

    problems = validate_edl(edl, project)
    if problems:
        for problem in problems:
            print(f"  EDL ERROR: {problem}", file=sys.stderr)
        return 1

    plan = plan_from_edl(edl, project, fit=args.fit, audio_input=args.audio_input, take=args.take)
    text = json.dumps(plan, indent=2, ensure_ascii=False) + "\n"

    if args.stdout:
        sys.stdout.write(text)
    elif args.out or pack is not None:
        out = Path(args.out) if args.out else (pack / "plan.json")
        if not out.is_absolute():
            out = resolve_path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"wrote {out}")
        print(summarize(plan))
    else:
        print("nowhere to write the plan: pass --out or --stdout", file=sys.stderr)
        return 2

    if args.emit_graph:
        graph_dir = Path(args.emit_graph)
        graph_dir.mkdir(parents=True, exist_ok=True)
        try:
            graphs = {window["id"]: build_window_graph(plan, window)
                      for window in plan["windows"]}
        except ValueError as exc:
            print(f"  cannot build graphs: {exc}", file=sys.stderr)
            return 2
        for window_id, graph in graphs.items():
            (graph_dir / f"w{window_id:02d}.json").write_text(
                json.dumps(graph, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"  wrote {len(graphs)} graphs to {graph_dir}")

    if args.strict and plan["warnings"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
