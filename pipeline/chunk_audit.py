#!/usr/bin/env python
"""Chunk audit: judge every rendered chunk against its intended shot, collect
scores, and print a ranked redo list. Uses qwen3.7-flash as the video judge."""
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATE = HERE / "state.json"
API = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "qwen/qwen3.7-flash"
REPORT = HERE / "audit_report.jsonl"

RUBRIC = (
    "You are auditing one shot of an ink/watercolor storybook music video. "
    "Score 0-10 each: fidelity (does the video honor the storyboard panel's composition, "
    "staging, camera and subjects), style (pure hand-drawn ink and watercolor storybook — "
    "no photoreal, no 3D, no plastic), motion (smooth, coherent, no morphing/glitches), "
    "audio (present, coherent with the scene, no harsh artifacts), and overall. "
    "Call out in ISSUES: what specifically fails and what would fix it (prompt, refs, "
    "settings). Reply ONLY with JSON: "
    '{"scores":{"fidelity":0,"style":0,"motion":0,"audio":0,"overall":0},'
    '"issues":["..."],"praise":["..."]}'
)


def call_judge(video_b64, prompt, key):
    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": RUBRIC},
            {"role": "user", "content": [
                {"type": "text", "text": f"INTENDED SHOT (the storyboard panel + prompt for this chunk):\n{prompt[:900]}"},
                {"type": "video_url", "video_url": {"url": video_b64}},
            ]},
        ],
        "temperature": 0.2,
    }
    req = urllib.request.Request(API, data=json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {key}",
                                          "Content-Type": "application/json"})
    last = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                d = json.load(r)
            txt = d["choices"][0]["message"]["content"]
            txt = txt.strip()
            if txt.startswith("```"):
                txt = txt.split("\n", 1)[1] if "\n" in txt else txt
                if txt.endswith("```"):
                    txt = txt[:-3]
            return json.loads(txt)
        except Exception as e:
            last = str(e)[:120]
            time.sleep(10 * (attempt + 1))  # backoff for rate limits
    return {"scores": {"overall": 0}, "issues": [f"judge call failed: {last}"]}


def main():
    key = os.environ.get("OPENROUTER_API_KEY") or ""
    if not key:
        kf = Path(__file__).resolve().parent.parent / "dashboard" / ".openrouter_key"
        if kf.is_file():
            key = kf.read_text(encoding="utf-8").strip()
    if not key:
        print("no OPENROUTER_API_KEY"); sys.exit(1)

    import base64
    import subprocess
    FFMPEG = r"C:/Users/adaml/AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-8.1.2-full_build/bin/ffmpeg.exe"
    s = json.loads(STATE.read_text(encoding="utf-8"))
    chunks = sorted([c for c in s["chunks"] if c.get("status") == "done" and c.get("output")],
                    key=lambda c: c["id"])
    # skip chunks already scored (overall > 0) in a previous run
    scored = set()
    if REPORT.is_file():
        for line in REPORT.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
                if r.get("scores", {}).get("overall", 0) > 0:
                    scored.add(r.get("chunk"))
            except Exception:
                pass
    todo = [c for c in chunks if c["id"] not in scored]
    print(f"auditing {len(todo)} chunks (skipping {len(chunks)-len(todo)} already scored) ...")
    results = []
    for c in todo:
        vp = Path(c["output"])
        if not vp.is_file():
            print(f"  #{c['id']} missing output — skip"); continue
        # compress to 540p for the judge (keeps payloads small and calls fast)
        small = vp.with_name(vp.stem + "_judge.mp4")
        subprocess.run([FFMPEG, "-y", "-i", str(vp), "-vf", "scale=-2:540",
                        "-c:v", "libx264", "-crf", "28", "-preset", "fast",
                        "-an", str(small)], capture_output=True)
        src = small if small.is_file() else vp
        b64 = "data:video/mp4;base64," + base64.b64encode(src.read_bytes()).decode()
        intended = c.get("prompt_override") or c.get("prompt") or c.get("name", "")
        r = call_judge(b64, intended, key)
        sc = r.get("scores", {})
        rec = {"chunk": c["id"], "name": c.get("name", ""), "video": vp.name,
               "scores": sc, "issues": r.get("issues", []), "praise": r.get("praise", [])}
        results.append(rec)
        with open(REPORT, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        print(f"  #{c['id']:>2} overall {sc.get('overall', 0)} | f {sc.get('fidelity', 0)} "
              f"s {sc.get('style', 0)} m {sc.get('motion', 0)} a {sc.get('audio', 0)}")
        time.sleep(1)

    print("\n=== RANKED (worst first — redo candidates) ===")
    for r in sorted(results, key=lambda x: x["scores"].get("overall", 0))[:10]:
        sc = r["scores"]
        top = (r["issues"] or ["—"])[0][:110]
        print(f"  #{r['chunk']:>2} {sc.get('overall', 0):>4} | {top}")


if __name__ == "__main__":
    main()
