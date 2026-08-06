#!/usr/bin/env python
"""Sample battery: after production completes, render N settings variants of one
prompt through the dashboard /api/generate, judge them with qwen3.7-flash, and
print a scored table for the operator to pick from."""
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATE = HERE / "state.json"
DASH = "http://127.0.0.1:8787"

PROMPT = ("that episode of friends where Fry from Futurama started dating Rachel "
          "and it was sort-of gross")

VARIANTS = [
    {"name": "base_t20_beta_t13", "steps": 20, "scheduler": "beta", "tau": 1.3, "sol": True},
    {"name": "steps30", "steps": 30, "scheduler": "beta", "tau": 1.3, "sol": True},
    {"name": "sched_simple", "steps": 20, "scheduler": "simple", "tau": 1.3, "sol": True},
    {"name": "sched_normal", "steps": 20, "scheduler": "normal", "tau": 1.3, "sol": True},
    {"name": "tau10", "steps": 20, "scheduler": "beta", "tau": 1.0, "sol": True},
    {"name": "tau16", "steps": 20, "scheduler": "beta", "tau": 1.6, "sol": True},
    {"name": "sol_off", "steps": 20, "scheduler": "beta", "tau": 1.3, "sol": False},
    {"name": "structured_prompt", "steps": 20, "scheduler": "beta", "tau": 1.3, "sol": True,
     "prompt": ("For the target video: a sitcom crossover where Fry from Futurama starts "
                "dating Rachel from Friends and it is sort-of gross.\n\n"
                "integrated_multimodal_description: [Shot 1] A medium two-shot on the Central "
                "Perk couch, 2D cartoon Fry in his orange jacket sitting awkwardly next to "
                "live-action Rachel in 90s denim, a slow push-in with small amplitude; Fry "
                "shows off a glowing alien slinky, Rachel reacts with polite disgust; studio "
                "sitcom lighting with warm practicals and audience laughter energy.\n\n"
                "overall_soundscape: sitcom audience laughter, soft couch creaks, the slinky "
                "humming faintly.\n\n"
                "non_diegetic_music: a light 90s sitcom comedy cue.")},
    {"name": "dur10s", "steps": 20, "scheduler": "beta", "tau": 1.3, "sol": True, "duration": "10s"},
    {"name": "res4x3", "steps": 20, "scheduler": "beta", "tau": 1.3, "sol": True, "resolution": "992x768 (4:3)"},
]


def http_json(url, method="GET", payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"} if payload else {})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def production_done():
    s = json.load(open(STATE, encoding="utf-8"))
    return all(c["status"] == "done" for c in s["chunks"])


def main():
    print("[battery] waiting for production to complete ...")
    while not production_done():
        time.sleep(60)
    print("[battery] production done — starting variant renders")
    jobs = []
    for v in VARIANTS:
        body = {
            "mode": "t2v",
            "prompt": v.get("prompt", PROMPT),
            "resolution": v.get("resolution", "832x480 (fast)"),
            "duration": v.get("duration", "5s"),
            "steps": v["steps"],
            "scheduler": v["scheduler"],
            "seed": 424242,
            "sol_attn": v["sol"],
            "tau": v["tau"],
        }
        for attempt in range(5):
            try:
                r = http_json(DASH + "/api/generate", "POST", body)
                break
            except Exception:
                time.sleep(10)
        if "prompt_id" in r:
            jobs.append((v["name"], r["prompt_id"]))
            print(f"  submitted {v['name']} -> {r['prompt_id'][:8]}")
        else:
            print(f"  FAILED {v['name']}: {r}")
        time.sleep(3)
    print("[battery] waiting for renders ...")
    results = {}
    while jobs:
        done = []
        for name, pid in jobs:
            try:
                st = http_json(DASH + f"/api/gen-status?prompt_id={pid}")
            except Exception:
                continue
            if st.get("status") == "done" and st.get("video"):
                results[name] = st["video"]
                print(f"  {name} DONE -> {st['video']}")
                done.append((name, pid))
            elif st.get("status") == "error":
                print(f"  {name} ERROR")
                done.append((name, pid))
        for d in done:
            jobs.remove(d)
        time.sleep(20)
    print("[battery] judging with qwen3.7-flash ...")
    clips = [str(Path(r"C:/ComfyUI/output") / results[n["name"]]) for n in VARIANTS if n["name"] in results]
    if not clips:
        print("no clips to judge"); sys.exit(1)
    judge = [sys.executable, str(HERE / "judge.py"), *clips,
             "--prompt", PROMPT, "--json"]
    subprocess.run(judge, env=dict(os.environ, PYTHONPATH=""))
    print("\n[battery] done — samples in C:/ComfyUI/output/video/gallery/")
    for n in VARIANTS:
        if n["name"] in results:
            print(f"  {n['name']}: /video/{results[n['name']]}")


if __name__ == "__main__":
    main()
