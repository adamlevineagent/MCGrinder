#!/usr/bin/env python
"""Honing harness: render test configs at low res through the seam kit,
inspect results, and log everything for the iteration loop.

Usage: python hone.py <config.json>   (config: list of test dicts)
Each test: {name, prompt, seam (mp4 path or image), refs: [files], audio: wav,
            width, height, length, steps, seed}
Outputs go to D:/ComfyUI/output/video/hone/<name>_<ts>.mp4; a report JSON is
appended to hone_report.jsonl with per-test frame-0 diff vs the seam frame.
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

COMFY = "http://127.0.0.1:8188"
HERE = Path(__file__).resolve().parent
REPORT = HERE / "hone_report.jsonl"

NODES = {
    "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "minimax_h3_ref2va_pruned_fp8_scaled.safetensors", "weight_dtype": "default"}},
    "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors", "type": "minimax"}},
    "3": {"class_type": "VAELoader", "inputs": {"vae_name": "minimax_h3_video_vae_fp16.safetensors"}},
    "4": {"class_type": "VAELoader", "inputs": {"vae_name": "minimax_h3_audio_vae_fp32.safetensors"}},
    "5": {"class_type": "MiniMaxH3SigmaShift", "inputs": {"model": ["1", 0], "shift_video": 12.0, "shift_audio": 3.0}},
}


def http_json(path, data=None):
    req = urllib.request.Request(COMFY + path,
                                 data=json.dumps(data).encode() if data else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def build_workflow(t):
    nid = 6
    nodes = dict(NODES)
    seam_input = None
    if t.get("seam_mp4"):
        seam = t["seam_mp4"]
        nodes[str(nid)] = {"class_type": "SeamFrame", "inputs": {"video_path": seam, "mode": "last"}}
        seam_input = [str(nid), 0]
        nid += 1
    elif t.get("seam_image"):
        nodes[str(nid)] = {"class_type": "LoadImage", "inputs": {"image": t["seam_image"]}}
        seam_input = [str(nid), 0]
        nid += 1
    ref_inputs = {}
    for i, ref in enumerate(t.get("refs", []), start=1):
        nodes[str(nid)] = {"class_type": "LoadImage", "inputs": {"image": ref}}
        ref_inputs[f"ref_image_{i}"] = [str(nid), 0]
        nid += 1
    audio_input = None
    if t.get("audio_wav"):
        nodes[str(nid)] = {"class_type": "LoadAudio", "inputs": {"audio": t["audio_wav"]}}
        load_id = nid
        nid += 1
        if t.get("audio_mode", "pulse") == "pulse":
            nodes[str(nid)] = {"class_type": "BeatPulse", "inputs": {"audio": [str(load_id), 0], "pulse_type": t.get("pulse_type", "kick"), "gain": t.get("pulse_gain", 1.0)}}
            audio_input = [str(nid), 0]
            nid += 1
        else:
            audio_input = [str(load_id), 0]
    seam_inp = {"clip": ["2", 0], "vae": ["3", 0], "audio_vae": ["4", 0],
                "prompt": t["prompt"], "width": t.get("width", 832), "height": t.get("height", 480),
                "length": t.get("length", 124), "ref_image_size": t.get("ref_image_size", "match")}
    if seam_input:
        seam_inp["first_frame"] = seam_input
    seam_inp.update(ref_inputs)
    if audio_input:
        seam_inp["ref_audio_1"] = audio_input
    nodes[str(nid)] = {"class_type": "MiniMaxH3SeamToVideo", "inputs": seam_inp}
    h3 = str(nid)
    nid += 1
    nodes[str(nid)] = {"class_type": "RandomNoise", "inputs": {"noise_seed": t.get("seed", 424242)}}
    noise = str(nid); nid += 1
    nodes[str(nid)] = {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "res_multistep"}}
    samp = str(nid); nid += 1
    nodes[str(nid)] = {"class_type": "BasicScheduler", "inputs": {"model": ["5", 0], "scheduler": "simple", "steps": t.get("steps", 20), "denoise": 1.0}}
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
    nodes[str(nid)] = {"class_type": "SaveVideo", "inputs": {"video": [cv, 0], "filename_prefix": f"video/hone/{t['name']}", "format": "auto", "codec": "auto"}}
    return nodes


def wait_for(prompt_id, timeout=2400):
    t0 = time.time()
    while time.time() - t0 < timeout:
        hist = http_json(f"/history/{prompt_id}")
        if hist and prompt_id in hist:
            return hist[prompt_id]
        time.sleep(30)
    return None


def main():
    cfg_path = sys.argv[1]
    tests = json.loads(open(cfg_path, encoding="utf-8").read())
    tests = tests if isinstance(tests, list) else [tests]
    for t in tests:
        name = t["name"]
        print(f"[hone] submitting {name} ...")
        wf = build_workflow(t)
        resp = http_json("/prompt", {"prompt": wf, "client_id": "hone"})
        if "prompt_id" not in resp:
            print(f"[hone] {name} SUBMIT FAIL: {str(resp)[:200]}")
            continue
        pid = resp["prompt_id"]
        entry = wait_for(pid)
        if entry is None:
            print(f"[hone] {name} TIMEOUT")
            continue
        st = (entry.get("status") or {}).get("status_str")
        out = None
        for nid, o in (entry.get("outputs") or {}).items():
            for k, v in o.items():
                if isinstance(v, list):
                    for item in v:
                        if not isinstance(item, dict):
                            continue
                        if item.get("type") == "output" and item.get("filename", "").endswith(".mp4"):
                            out = item
        rec = {"name": name, "prompt_id": pid, "status": st,
               "output": out and out.get("filename"),
               "config": {k: t[k] for k in ("prompt", "audio_mode", "width", "height", "length", "steps", "seed") if k in t},
               "ts": time.strftime("%Y-%m-%d %H:%M:%S")}
        if st == "error":
            for m in (entry.get("status") or {}).get("messages", []):
                if m[0] == "execution_error":
                    rec["error"] = m[1].get("exception_message", "")[:300]
        print(f"[hone] {name} -> {st} {out and out['filename']}")
        with open(REPORT, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")


if __name__ == "__main__":
    main()
