"""Load machine-local MCGrinder config. Never commit config.json.

Search order: $MCGRINDER_CONFIG, then <repo>/config.json.
Does not fall back to config.example.json — that file is a template.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent

_DEFAULT_FFMPEG = (
    r"C:/Users/adaml/AppData/Local/Microsoft/WinGet/Packages/"
    r"Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/"
    r"ffmpeg-8.1.2-full_build/bin/ffmpeg.exe"
)
_DEFAULT_LAUNCH = [
    "--use-sage-attention", "--cache-classic",
    "--enable-cors-header", "*", "--port", "8188",
]


def repo_root() -> Path:
    return REPO_ROOT


def config_candidates() -> list[Path]:
    out = []
    env = os.environ.get("MCGRINDER_CONFIG")
    if env:
        out.append(Path(env))
    out.append(REPO_ROOT / "config.json")
    return out


def load_config() -> dict:
    """Return the operator config dict, or {} if none is present."""
    for path in config_candidates():
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError(f"config must be a JSON object: {path}")
            data["_config_path"] = str(path)
            return data
    return {}


def resolve_path(value, default=None) -> Path | None:
    if value in (None, ""):
        value = default
    if value in (None, ""):
        return None
    path = Path(value)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path


def state_path(cfg=None) -> Path:
    cfg = load_config() if cfg is None else cfg
    return resolve_path(cfg.get("state_file"), HERE / "state.json")


def beats_path(cfg=None) -> Path:
    cfg = load_config() if cfg is None else cfg
    return resolve_path(cfg.get("beats_file"), HERE / "beats.json")


def pack_dir(cfg=None) -> Path | None:
    cfg = load_config() if cfg is None else cfg
    return resolve_path(cfg.get("pack"))


def comfy_url(cfg=None) -> str:
    cfg = load_config() if cfg is None else cfg
    return (cfg.get("comfy") or {}).get("url") or "http://127.0.0.1:8188"


def comfy_dir(cfg=None) -> Path:
    cfg = load_config() if cfg is None else cfg
    return resolve_path((cfg.get("comfy") or {}).get("dir"), Path(r"C:/ComfyUI"))


def comfy_output_dir(cfg=None) -> Path:
    cfg = load_config() if cfg is None else cfg
    comfy = cfg.get("comfy") or {}
    return resolve_path(comfy.get("output_dir"), comfy_dir(cfg) / "output")


def venv_python(cfg=None) -> Path:
    cfg = load_config() if cfg is None else cfg
    comfy = cfg.get("comfy") or {}
    return resolve_path(comfy.get("venv_python"), comfy_dir(cfg) / ".venv" / "Scripts" / "python.exe")


def ffmpeg_path(cfg=None) -> str:
    cfg = load_config() if cfg is None else cfg
    return cfg.get("ffmpeg") or _DEFAULT_FFMPEG


def launch_flags(cfg=None) -> list:
    cfg = load_config() if cfg is None else cfg
    return list((cfg.get("comfy") or {}).get("launch_flags") or _DEFAULT_LAUNCH)


def audio_mode_default(cfg=None, state=None) -> str:
    if state and state.get("audio_mode_default"):
        return state["audio_mode_default"]
    cfg = load_config() if cfg is None else cfg
    return cfg.get("audio_mode_default") or "pulse"


def chunk_audio_mode(chunk, cfg=None, state=None) -> str:
    """Per-chunk audio_mode always wins. Config/state default is fallback only."""
    mode = chunk.get("audio_mode")
    if mode:
        return mode
    return audio_mode_default(cfg, state)


def input_subdir(state) -> str:
    """Comfy LoadImage path prefix = the frames_dir folder name."""
    frames = state.get("frames_dir") or ""
    name = Path(frames).name
    return name or "mv_frames"


def project_slug(state) -> str:
    if state.get("slug"):
        return state["slug"]
    project = (state.get("project") or "mv").strip()
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in project.lower())
    return safe.strip("_") or "mv"
