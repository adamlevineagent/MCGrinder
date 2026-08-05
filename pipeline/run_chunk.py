#!/usr/bin/env python
"""BUSY music-video chunk worker (ref2va pipeline).

Per chunk:
  - extracts the previous chunk's LAST FRAME -> becomes ref_image_0 (seam)
  - extracts the chunk's exact SONG WINDOW (32kHz wav) -> ref_audio_0
  - adds the chunk's pack reference sheets (storyboard/characters/locations)
  - renders via MiniMaxH3ReferenceToVideo (style lock + audio sync)
  - immediately muxes the real song window onto the finished chunk
One invocation advances the pipeline one step (submit next / poll rendering).
Run with the ComfyUI venv python and cleared PYTHONPATH. Idempotent.
"""
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATE = HERE / "state.json"
COMFY = "http://127.0.0.1:8188"
COMFY_DIR = Path(r"D:/ComfyUI")
VENV_PY = COMFY_DIR / ".venv" / "Scripts" / "python.exe"
FFMPEG = r"C:/Users/adaml/AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-8.1.2-full_build/bin/ffmpeg.exe"
MAX_RETRIES = 2


def sh(cmd, timeout=1800):
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
    return r.stdout, r.returncode


def http_json(path, data=None):
    try:
        req = urllib.request.Request(COMFY + path,
                                     data=json.dumps(data).encode() if data else None,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except Exception:
        return None


def server_up():
    # /system_stats can 500 when the SQLite DB lock is held by a busy render,
    # so fall back to /queue (lightweight, always works once the server is up).
    for endpoint in ("/system_stats", "/queue"):
        try:
            with urllib.request.urlopen(COMFY + endpoint, timeout=5) as r:
                if r.status == 200:
                    return True
        except Exception:
            continue
    return False


def start_server():
    print("  server down -> starting ComfyUI")
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    log = open(HERE / "comfy_server.log", "a", encoding="utf-8")
    subprocess.Popen([str(VENV_PY), "main.py", "--use-sage-attention", "--cache-classic",
                      "--enable-cors-header", "*", "--port", "8188"],
                     cwd=str(COMFY_DIR), env=env, stdout=log, stderr=subprocess.STDOUT,
                     creationflags=0x00000008)
    for _ in range(120):
        time.sleep(2)
        if server_up():
            print("  server up")
            return True
    return False


def align_frames(duration_s):
    n = max(5, int(duration_s * 24))
    while n % 17 != 5:
        n += 1
    return n


def load_state():
    return json.loads(STATE.read_text(encoding="utf-8"))


def save_state(s):
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(s, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(STATE)


def prep_inputs(chunk, state):
    """Create the seam frame + song window for this chunk. Returns (frame_file, wav_file)."""
    frames_dir = Path(state["frames_dir"])
    frames_dir.mkdir(parents=True, exist_ok=True)
    out_dir = Path(state["output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)

    # seam frame: previous chunk's last frame (or the pack image for chunk 1)
    if chunk["first_frame"] == "prev_last":
        prev = next((c for c in state["chunks"] if c["id"] == chunk["id"] - 1), None)
        if not prev or not prev.get("output"):
            raise RuntimeError(f"previous chunk {chunk['id']-1} has no output yet")
        prev_mp4 = Path(prev["output"])
        if not prev_mp4.is_file():
            raise RuntimeError(f"previous output missing: {prev_mp4}")
        frame_png = frames_dir / f"chunk_{chunk['id']:02d}_first.png"
        sh([FFMPEG, "-y", "-sseof", "-0.05", "-i", str(prev_mp4), "-frames:v", "1",
            "-q:v", "2", str(frame_png)])
        frame_file = f"busy_frames/chunk_{chunk['id']:02d}_first.png"
    else:
        frame_file = chunk["first_frame"]

    # song window for this chunk (32kHz stereo = audio VAE native rate)
    wav = frames_dir / f"chunk_{chunk['id']:02d}_audio.wav"
    sh([FFMPEG, "-y", "-ss", str(chunk["offset_s"]), "-t", str(chunk["duration_s"]),
        "-i", state["song"]["path"], "-ar", "32000", "-ac", "2", str(wav)])
    wav_file = f"busy_frames/chunk_{chunk['id']:02d}_audio.wav"
    return frame_file, wav_file


def build_workflow(chunk, frame_file, wav_file, frames, style_block, refs,
                   width=1344, height=768):
    """Seam-kit workflow: PINNED first frame (prev chunk's last frame) + pack
    refs + song window (pulse by default, raw for singer scenes) via
    MiniMaxH3SeamToVideo. <Picture N> tags map 1:1 to refs (seam is untagged)."""
    prompt = (chunk.get("prompt_override") or chunk["prompt"]) + " " + style_block
    audio_mode = chunk.get("audio_mode", "raw")  # raw = song window (music present); pulse = rhythm-only
    nid = 7
    nodes = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "minimax_h3_ref2va_pruned_fp8_scaled.safetensors", "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors", "type": "minimax"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "minimax_h3_video_vae_fp16.safetensors"}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": "minimax_h3_audio_vae_fp32.safetensors"}},
        "5": {"class_type": "MiniMaxH3SigmaShift", "inputs": {"model": ["1", 0], "shift_video": 12.0, "shift_audio": 3.0}},
        "6": {"class_type": "LoadImage", "inputs": {"image": frame_file}},  # seam frame -> PINNED first_frame
    }
    inp = {
        "clip": ["2", 0], "vae": ["3", 0], "audio_vae": ["4", 0],
        "prompt": prompt, "width": width, "height": height, "length": frames,
        "ref_image_size": "match",
        "first_frame": ["6", 0],
    }
    for i, ref in enumerate(refs, start=1):
        nodes[str(nid)] = {"class_type": "LoadImage", "inputs": {"image": ref}}
        inp[f"ref_image_{i}"] = [str(nid), 0]
        nid += 1
    # song window -> pulse (rhythm only, no vocals) or raw
    nodes[str(nid)] = {"class_type": "LoadAudio", "inputs": {"audio": wav_file}}
    audio_src = str(nid)
    nid += 1
    if audio_mode == "pulse":
        nodes[str(nid)] = {"class_type": "BeatPulse", "inputs": {"audio": [audio_src, 0], "pulse_type": chunk.get("pulse_type", "kick"), "gain": chunk.get("pulse_gain", 1.0)}}
        inp["ref_audio_1"] = [str(nid), 0]
        nid += 1
    else:
        inp["ref_audio_1"] = [audio_src, 0]
    h3 = str(nid)
    nodes[h3] = {"class_type": "MiniMaxH3SeamToVideo", "inputs": inp}
    nid += 1
    nodes[str(nid)] = {"class_type": "RandomNoise", "inputs": {"noise_seed": 1000 + chunk["id"] * 977 + chunk.get("redo", 0) * 7919}}
    noise = str(nid); nid += 1
    nodes[str(nid)] = {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "res_multistep"}}
    samp = str(nid); nid += 1
    nodes[str(nid)] = {"class_type": "BasicScheduler", "inputs": {"model": ["5", 0], "scheduler": "simple", "steps": 20, "denoise": 1.0}}
    sched = str(nid); nid += 1
    nodes[str(nid)] = {"class_type": "BasicGuider", "inputs": {"model": ["5", 0], "conditioning": [h3, 0]}}
    guid = str(nid); nid += 1
    nodes[str(nid)] = {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": [noise, 0], "guider": [guid, 0], "sampler": [samp, 0], "sigmas": [sched, 0], "latent_image": [h3, 1]}}
    smp = str(nid); nid += 1
    nodes[str(nid)] = {"class_type": "VAEDecode", "inputs": {"samples": [smp, 0], "vae": ["3", 0]}}
    dec = str(nid); nid += 1
    nodes[str(nid)] = {"class_type": "VAEDecodeAudio", "inputs": {"samples": [smp, 0], "vae": ["4", 0]}}
    deca = str(nid); nid += 1
    nodes[str(nid)] = {"class_type": "CreateVideo", "inputs": {"images": [dec, 0], "fps": 24, "audio": [deca, 0], "bit_depth": 8}}
    cv = str(nid); nid += 1
    nodes[str(nid)] = {"class_type": "SaveVideo", "inputs": {"video": [cv, 0], "filename_prefix": f"video/busy_mv/chunk_{chunk['id']:02d}", "format": "auto", "codec": "auto"}}
    return nodes


def mux_song(chunk, raw_mp4, state):
    """Overlay the chunk's exact song window so the chunk itself carries the real audio."""
    song_out = Path(raw_mp4).with_name(f"{Path(raw_mp4).stem}_song.mp4")
    sh([FFMPEG, "-y", "-i", str(raw_mp4), "-ss", str(chunk["offset_s"]),
        "-i", state["song"]["path"],
        "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac",
        "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(song_out)])
    return str(song_out) if song_out.is_file() else str(raw_mp4)


def submit(chunk, state):
    frames = align_frames(chunk["duration_s"])
    frame_file, wav_file = prep_inputs(chunk, state)
    refs = chunk.get("refs_override") or chunk.get("refs", [])
    if not refs:
        refs = ["busy_refs/01_01_storyboard_panels_01-04_silhouette_prologue.png"]
    wf = build_workflow(chunk, frame_file, wav_file, frames, state["style_block"], refs,
                        width=state.get("width", 1344), height=state.get("height", 768))
    resp = http_json("/prompt", {"prompt": wf, "client_id": "busy-mv-worker"})
    if not resp or "prompt_id" not in resp:
        return f"  chunk {chunk['id']}: submit failed: {str(resp)[:200]}"
    chunk["prompt_id"] = resp["prompt_id"]
    chunk["status"] = "rendering"
    save_state(state)
    return f"  chunk {chunk['id']} SUBMITTED ({resp['prompt_id']}) — {chunk['name']}"


def trim_to_window(chunk, mp4):
    """Trim a rendered chunk to EXACTLY its song window (duration_s).

    The 17k+5 frame grid renders ~0.1-0.6s longer than the window; untrimmed
    that drift compounds across chunks and the song falls out of sync. Re-encode
    with libx264 veryfast (sub-second at 1344x768), in place."""
    tmp = Path(mp4).with_name(Path(mp4).stem + "_trim.mp4")
    sh([FFMPEG, "-y", "-i", str(mp4), "-t", str(chunk["duration_s"]),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "16",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(tmp)])
    if tmp.is_file():
        os.replace(tmp, mp4)
        return True
    return False


def poll(chunk, state):
    pid = chunk.get("prompt_id")
    if not pid:
        chunk["status"] = "pending"
        save_state(state)
        return f"  chunk {chunk['id']}: no prompt_id, reset to pending"
    hist = http_json(f"/history/{pid}")
    entry = (hist or {}).get(pid)
    if not entry:
        # job not in history: is it actually alive in the queue?
        q = http_json("/queue") or {}
        alive = any(
            (isinstance(e, list) and len(e) > 1 and e[1] == pid)
            for e in (q.get("queue_running", []) or []) + (q.get("queue_pending", []) or [])
        )
        if not alive:
            chunk["status"] = "pending"
            chunk["prompt_id"] = None
            save_state(state)
            return f"  chunk {chunk['id']}: job vanished (server restart?) — reset to pending"
        return f"  chunk {chunk['id']}: still rendering (no history yet)"
    st = (entry.get("status") or {}).get("status_str")
    if st == "success":
        out = None
        for nid, o in (entry.get("outputs") or {}).items():
            for k, v in o.items():
                if isinstance(v, list):
                    for item in v:
                        if not isinstance(item, dict):
                            continue
                        if item.get("type") == "output" and item.get("filename", "").endswith(".mp4"):
                            out = item
        if out:
            raw = Path(r"D:/ComfyUI/output") / (out.get("subfolder") or "") / out["filename"]
            if raw.is_file():
                trim_to_window(chunk, raw)
                chunk["output"] = str(raw)
                chunk["status"] = "done"
                save_state(state)
                return f"  chunk {chunk['id']} DONE -> {raw.name}"
        chunk["errors"] = chunk.get("errors", 0) + 1
        chunk["status"] = "failed" if chunk["errors"] >= MAX_RETRIES else "pending"
        save_state(state)
        return f"  chunk {chunk['id']}: success but no output found — retry"
    if st == "error":
        msg = ""
        for m in (entry.get("status") or {}).get("messages", []):
            if m[0] == "execution_error":
                msg = str(m[1].get("exception_message", ""))[:200]
        chunk["errors"] = chunk.get("errors", 0) + 1
        chunk["status"] = "failed" if chunk["errors"] >= MAX_RETRIES else "pending"
        chunk["prompt_id"] = None
        save_state(state)
        return f"  chunk {chunk['id']} ERROR (try {chunk['errors']}/{MAX_RETRIES}): {msg}"
    return f"  chunk {chunk['id']}: running ({st})"


def main():
    if not server_up():
        if not start_server():
            print("  FATAL: could not start ComfyUI")
            sys.exit(1)
    state = load_state()
    chunks = state["chunks"]
    pending = [c for c in chunks if c["status"] == "pending"]
    rendering = [c for c in chunks if c["status"] == "rendering"]
    done = [c for c in chunks if c["status"] == "done"]
    print(f"  state: {len(done)} done, {len(rendering)} rendering, {len(pending)} pending, "
          f"{len([c for c in chunks if c['status']=='failed'])} failed")
    if rendering:
        print(poll(rendering[0], state))
        # if that chunk just completed, immediately start the next one
        re = json.loads(STATE.read_text(encoding="utf-8"))
        if not any(c["status"] == "rendering" for c in re["chunks"]):
            nxt = next((c for c in re["chunks"] if c["status"] == "pending"), None)
            if nxt:
                print(submit(nxt, re))
    elif pending:
        print(submit(pending[0], state))
    else:
        failed = [c for c in chunks if c["status"] == "failed"]
        if failed:
            print(f"  ALL BLOCKED: failed chunks: " + ", ".join(str(c["id"]) for c in failed))
        else:
            print("  ALL CHUNKS DONE — run stitch.py for the final video")


if __name__ == "__main__":
    main()
