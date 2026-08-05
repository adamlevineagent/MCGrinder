#!/usr/bin/env python
"""H3 music-video dashboard — a window into the local ComfyUI H3 pipeline.

Serves:
  /               the dashboard UI
  /api/status     ComfyUI health, GPU, live queue (with parsed prompts)
  /api/videos     gallery of generated outputs (ffprobe + embedded prompt metadata)
  /api/workflows  the H3 template/workflow JSONs we use
  /video/<rel>    range-request mp4 serving from the ComfyUI output dir
"""
import json
import os
import subprocess
import threading
import time
import urllib.request
from pathlib import Path

from flask import Flask, abort, jsonify, send_from_directory

COMFY = "http://127.0.0.1:8188"
HERE = Path(__file__).resolve().parent
OUTPUT_DIR = Path(r"D:/ComfyUI/output")
WORKFLOW_DIR = Path(r"D:/ComfyUI-setup/workflows")
FFPROBE = r"C:/Users/adaml/AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-8.1.2-full_build/bin/ffprobe.exe"
FFPROBE = os.environ.get("FFPROBE", FFPROBE)
NVIDIA_SMI = r"C:/Windows/System32/nvidia-smi.exe"

app = Flask(__name__)

# keep the terminal quiet: werkzeug access logs go to a file, not stdout
import logging
_wz = logging.getLogger("werkzeug")
_wz.setLevel(logging.INFO)
try:
    _fh = logging.FileHandler(HERE / "dashboard.log", encoding="utf-8")
    _fh.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    _wz.handlers = [_fh]
except Exception:
    _wz.setLevel(logging.WARNING)

# ---------------------------------------------------------------- helpers

def sh(cmd, timeout=30):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout
    except Exception:
        return ""


def comfy_get(path):
    try:
        with urllib.request.urlopen(COMFY + path, timeout=10) as r:
            return json.load(r)
    except Exception:
        return None


_gpu = {"t": 0.0, "data": None}


def gpu_status():
    if time.time() - _gpu["t"] < 3:
        return _gpu["data"]
    out = sh([NVIDIA_SMI, "--query-gpu=utilization.gpu,memory.used,memory.total",
              "--format=csv,noheader,nounits"])
    data = None
    try:
        u, mu, mt = (int(x.strip()) for x in out.strip().split(","))
        data = {"util": u, "vram_used_mb": mu, "vram_total_mb": mt}
    except Exception:
        data = None
    _gpu.update(t=time.time(), data=data)
    return data


def parse_workflow(wf):
    """Pull the human-relevant bits out of a ComfyUI API workflow dict."""
    s = {"kind": None, "prompt": None, "width": None, "height": None, "length": None,
         "seed": None, "steps": None, "sampler": None, "scheduler": None,
         "model": None, "text_encoder": None, "refs": [], "audio_refs": [], "nodes": {},
         "chunk_id": None}
    if not isinstance(wf, dict):
        return s
    import re
    for nid, n in wf.items():
        if not isinstance(n, dict):
            continue
        ct = n.get("class_type", "")
        inp = n.get("inputs", {}) or {}
        s["nodes"][str(nid)] = ct
        if ct == "SaveVideo":
            m = re.search(r"chunk_(\d+)", str(inp.get("filename_prefix", "")))
            if m:
                s["chunk_id"] = int(m.group(1))
        if ct == "MiniMaxH3ImageToVideo":
            s["kind"] = "T2V / I2V (fl2va)"
            s["prompt"] = inp.get("prompt") or s["prompt"]
            s["width"] = inp.get("width") or s["width"]
            s["height"] = inp.get("height") or s["height"]
            s["length"] = inp.get("length") or s["length"]
        elif ct == "MiniMaxH3ReferenceToVideo":
            s["kind"] = "R2V (ref2va)"
            s["prompt"] = inp.get("prompt") or s["prompt"]
            s["width"] = inp.get("width") or s["width"]
            s["height"] = inp.get("height") or s["height"]
            s["length"] = inp.get("length") or s["length"]
            for k, v in inp.items():
                if k.startswith("ref_images."):
                    s["refs"].append(v if isinstance(v, str) else f"node {v[0]}")
                elif k.startswith("ref_audios."):
                    s["audio_refs"].append(v if isinstance(v, str) else f"node {v[0]}")
        elif ct == "RandomNoise" and s["seed"] is None:
            s["seed"] = inp.get("noise_seed")
        elif ct == "BasicScheduler" and s["steps"] is None:
            s["steps"] = inp.get("steps")
            s["scheduler"] = inp.get("scheduler")
        elif ct == "KSamplerSelect" and s["sampler"] is None:
            s["sampler"] = inp.get("sampler_name")
        elif ct == "UNETLoader" and s["model"] is None:
            s["model"] = inp.get("unet_name")
        elif ct == "CLIPLoader" and s["text_encoder"] is None:
            s["text_encoder"] = inp.get("clip_name")
    return s


# ---------------------------------------------------------------- video scan

_videos = {"t": 0.0, "data": None}


def probe_mp4(path: Path):
    try:
        p = str(path).replace("/", "\\")
        raw = sh([FFPROBE, "-v", "quiet", "-print_format", "json",
                  "-show_format", "-show_streams", p])
        d = json.loads(raw or "{}")
        fmt = d.get("format", {})
        streams = d.get("streams", [])
        vstream = next((s for s in streams if s.get("codec_type") == "video"), {})
        astream = next((s for s in streams if s.get("codec_type") == "audio"), None)
        wf = None
        try:
            wf = json.loads((fmt.get("tags", {}) or {}).get("prompt", ""))
        except Exception:
            wf = None
        return {
            "duration": round(float(fmt.get("duration", 0)), 2),
            "width": vstream.get("width"),
            "height": vstream.get("height"),
            "fps": vstream.get("avg_frame_rate"),
            "has_audio": astream is not None,
            "audio_codec": (astream or {}).get("codec_name"),
            "summary": parse_workflow(wf) if wf else {},
        }
    except Exception:
        return {"duration": 0, "width": None, "height": None, "has_audio": False, "summary": {}}


def list_videos():
    if time.time() - _videos["t"] < 10:
        return _videos["data"]
    items = []
    try:
        files = sorted(OUTPUT_DIR.rglob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    except Exception:
        files = []
    for p in files:
        try:
            st = p.stat()
        except Exception:
            continue
        meta = probe_mp4(p)
        items.append({
            "name": p.name,
            "rel": str(p.relative_to(OUTPUT_DIR)).replace("\\", "/"),
            "size_mb": round(st.st_size / 1e6, 1),
            "mtime": st.st_mtime,
            **meta,
        })
    _videos.update(t=time.time(), data=items)
    return items


# ---------------------------------------------------------------- routes

@app.get("/")
def index():
    resp = send_from_directory(HERE, "index.html")
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/api/status")
def api_status():
    q = comfy_get("/queue")
    running = []
    for entry in (q or {}).get("queue_running", []) or []:
        if not isinstance(entry, list) or len(entry) < 3:
            continue
        running.append({
            "prompt_id": entry[1],
            "summary": parse_workflow(entry[2]),
            "created": (entry[3] or {}).get("create_time") if isinstance(entry[3], dict) else None,
        })
    pending = len((q or {}).get("queue_pending", []) or [])
    return jsonify({
        "comfy_up": q is not None,
        "gpu": gpu_status(),
        "running": running,
        "pending": pending,
    })


@app.get("/api/videos")
def api_videos():
    return jsonify(list_videos())


@app.get("/api/workflows")
def api_workflows():
    out = []
    for p in sorted(WORKFLOW_DIR.glob("*.json")):
        if p.name.endswith("_payload.json") or p.name.startswith("h3_"):
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        wf = d.get("prompt") if isinstance(d, dict) and "prompt" in d else d
        out.append({"name": p.name, "summary": parse_workflow(wf)})
    return jsonify(out)


@app.get("/video/<path:rel>")
def video(rel):
    full = (OUTPUT_DIR / rel).resolve()
    if not str(full).startswith(str(OUTPUT_DIR.resolve())):
        abort(404)
    if not full.is_file():
        abort(404)
    return send_from_directory(OUTPUT_DIR, rel, conditional=True)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8787, debug=False, threaded=True)
