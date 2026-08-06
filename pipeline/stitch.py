#!/usr/bin/env python
"""BUSY final assembly: concat all done chunks in order, mux the full song,
write the finished music video. Idempotent — only runs when all 20 chunks done."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATE = HERE / "state.json"
FFMPEG = r"C:/Users/adaml/AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-8.1.2-full_build/bin/ffmpeg.exe"
FINAL_DIR = Path(r"C:/ComfyUI/output/video/busy_mv")


def sh(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.stdout + r.stderr, r.returncode


def main():
    state = json.loads(STATE.read_text(encoding="utf-8"))
    chunks = state["chunks"]
    done = [c for c in chunks if c["status"] == "done"]
    if not done:
        print("no chunks done yet")
        sys.exit(0)
    partial = len(done) < len(chunks)
    ordered = sorted(done, key=lambda c: c["id"])

    # up-to-date guard: restart ticks re-run this; skip unless something changed
    final = FINAL_DIR / ("BUSY_music_video_preview.mp4" if partial else "BUSY_music_video.mp4")
    if final.is_file():
        newest_input = 0.0
        for c in ordered:
            p = Path(c.get("output") or "")
            if p.is_file():
                newest_input = max(newest_input, p.stat().st_mtime)
        song_p = Path(state["song"]["path"])
        if song_p.is_file():
            newest_input = max(newest_input, song_p.stat().st_mtime)
        if final.stat().st_mtime > newest_input:
            print(f"up to date: {final.name} — skipping stitch")
            sys.exit(0)

    # 1) concat (in storyboard order)
    list_file = HERE / "concat.txt"
    list_file.write_text("\n".join(f"file '{c['output'].replace(chr(39), chr(39)+chr(39)+chr(39))}'"
                                   for c in ordered),
                         encoding="utf-8")
    full = FINAL_DIR / ("busy_preview.mp4" if partial else "busy_full.mp4")
    out, rc = sh([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
                  "-c", "copy", str(full)])
    if rc != 0 or not full.is_file():
        print("concat failed:", out[-500:])
        sys.exit(1)

    # 2) mux the REAL song over the concat (H3's internal audio drifts at seams;
    #    the real track is sample-accurate and this pass is sub-second).
    #    The video timeline IS the song timeline (chunk offsets are song offsets),
    #    so the track plays linearly from 0:00 across the whole video.
    raw_final = FINAL_DIR / ("busy_preview_song.mp4" if partial else "busy_full_song.mp4")
    out, rc = sh([FFMPEG, "-y", "-i", str(full), "-i", state["song"]["path"],
                  "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac",
                  "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(raw_final)])
    if rc != 0 or not raw_final.is_file():
        print("song mux failed:", out[-300:])
        sys.exit(1)
    final = FINAL_DIR / ("BUSY_music_video_preview.mp4" if partial else "BUSY_music_video.mp4")
    if final.exists():
        final.unlink()
    raw_final.replace(final)

    # 3) copy to Downloads
    dl = Path.home() / "Downloads" / final.name
    shutil.copy2(final, dl)
    print(f"{'PREVIEW' if partial else 'FINAL'} VIDEO: {final}  ({final.stat().st_size/1e6:.1f} MB, {len(ordered)}/{len(chunks)} chunks)")
    print(f"also at: {dl}")
    if partial:
        print(f"note: {len(chunks)-len(done)} chunks still to render")


if __name__ == "__main__":
    main()
