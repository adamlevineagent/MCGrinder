#!/usr/bin/env python
"""H3 video judge — sends renders to qwen3.7-flash (OpenRouter, video input) and
gets structured critiques + settings recommendations.

Usage:
  python judge.py clip_a.mp4 clip_b.mp4 ... [--prompt "intended shot"] [--rubric "extra criteria"]

Sends each video as a base64 data URL (local files aren't publicly reachable),
asks the judge for a scored JSON critique, appends to judge_report.jsonl, and
prints a comparison table.
"""
import argparse
import base64
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

API = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "qwen/qwen3.7-flash"
HERE = Path(__file__).resolve().parent
REPORT = HERE / "judge_report.jsonl"
FFMPEG = r"C:/Users/adaml/AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-8.1.2-full_build/bin/ffmpeg.exe"

JUDGE_SYSTEM = (
    "You are a video director and quality judge for AI-generated music-video clips. "
    "You watch short video clips and give precise, actionable critiques. "
    "Be specific about what is wrong (composition, character consistency, motion, "
    "artifacts, lip-sync, audio sync) and what settings changes would likely fix it "
    "(steps, scheduler, resolution, refs, prompt structure, denoise, seed strategy). "
    "Reply ONLY with a JSON object: "
    '{"scores":{"fidelity":0-10,"style":0-10,"motion":0-10,"audio":0-10,"overall":0-10},'
    '"issues":["..."],"praise":["..."],"recommendations":{"settings":{"steps":null,"scheduler":null,'
    '"resolution":null,"tau":null},"prompt_hint":"...","seed_strategy":"..."}}'
)

DEFAULT_RUBRIC = (
    "Judge visual quality, style adherence (ink/watercolor storybook), motion smoothness, "
    "audio coherence, character consistency, and any artifacts or text errors."
)


def encode_video(path: Path, max_mb: int = 18) -> str:
    """Base64 data URL for a local mp4; compresses via ffmpeg if too large."""
    if path.stat().st_size > max_mb * 1_000_000:
        tmp = path.with_name(path.stem + "_judge.mp4")
        subprocess.run([FFMPEG, "-y", "-i", str(path), "-vf", "scale=-2:540",
                        "-c:v", "libx264", "-crf", "28", "-preset", "fast",
                        "-an", str(tmp)], capture_output=True, check=True)
        path = tmp
    b64 = base64.b64encode(path.read_bytes()).decode()
    return f"data:video/mp4;base64,{b64}"


def call_judge(videos: list[str], prompt: str, rubric: str) -> dict:
    content = [{"type": "text",
                "text": f"INTENDED SHOT: {prompt}\n\nRUBRIC: {rubric}\n\n"
                        "Each attached video is one render. Critiques for each video, "
                        "clearly labeled by attachment order."}]
    for v in videos:
        content.append({"type": "video_url", "video_url": {"url": v}})
    body = {
        "model": MODEL,
        "messages": [{"role": "system", "content": JUDGE_SYSTEM},
                     {"role": "user", "content": content}],
        "temperature": 0.2,
    }
    req = urllib.request.Request(API, data=json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}",
                                          "Content-Type": "application/json"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                data = json.load(r)
            txt = data["choices"][0]["message"]["content"]
            return {"ok": True, "text": txt, "usage": data.get("usage", {})}
        except Exception as e:
            if attempt == 2:
                return {"ok": False, "error": str(e)}
            time.sleep(3)
    return {"ok": False, "error": "unreachable"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("videos", nargs="+", help="mp4 paths to judge")
    ap.add_argument("--prompt", default="", help="intended shot description")
    ap.add_argument("--rubric", default=DEFAULT_RUBRIC)
    ap.add_argument("--json", action="store_true", help="print raw judge text")
    args = ap.parse_args()

    if "OPENROUTER_API_KEY" not in os.environ:
        print("OPENROUTER_API_KEY not set"); sys.exit(1)

    encoded = []
    for v in args.videos:
        p = Path(v)
        if not p.is_file():
            print(f"missing: {v}"); sys.exit(1)
        print(f"encoding {p.name} ({p.stat().st_size//1024} KB)...")
        encoded.append(encode_video(p))

    print(f"judging {len(encoded)} clip(s) with {MODEL} ...")
    res = call_judge(encoded, args.prompt, args.rubric)
    if not res["ok"]:
        print("judge call failed:", res["error"]); sys.exit(1)

    record = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "prompt": args.prompt,
              "videos": [Path(v).name for v in args.videos],
              "text": res["text"], "usage": res["usage"]}
    with open(REPORT, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

    if args.json:
        print(res["text"])
    else:
        print("\n--- judge ---")
        print(res["text"][:2500])
    print(f"\nappended to {REPORT}")


if __name__ == "__main__":
    main()
