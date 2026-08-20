"""h3_edl_window nodes: feed a frame EDL plan into the live h3_seam_kit.

These three nodes exist because the installed kit cannot read a plan JSON. They
do not re-implement anything it already does:

  H3EDLWindow    -> the window's numbers (length / offset_s / duration_s / seed
                    / prompt), which drive SongWindow and MiniMaxH3SeamToVideo.
  H3EDLStill     -> the inject still as pixels, unresized and un-round-tripped,
                    for MiniMaxH3SeamToVideo's first_frame / last_frame.
  H3EDLSeamCheck -> proves window N's last still and window N+1's first still
                    are the same pixels, which is what makes the roll a roll.

Audio cropping stays SongWindow. First/last pinning stays MiniMaxH3SeamToVideo.
Pulling a frame back out of a rendered mp4 stays SeamFrame.
"""
from __future__ import annotations

import os

from . import plan_io

CATEGORY = "video/h3_edl"


def _mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return float("nan")


def _comfy_input_dir(input_dir):
    if input_dir:
        return input_dir
    try:
        import folder_paths
        return folder_paths.get_input_directory()
    except Exception:
        return None


class H3EDLWindow:
    """Read one window out of a plan_schema 1 file."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "plan_path": ("STRING", {"default": "", "multiline": False}),
                "window_id": ("INT", {"default": 1, "min": 1, "max": 4096}),
            },
            "optional": {
                "take": ("INT", {"default": 0, "min": 0, "max": 999}),
            },
        }

    RETURN_TYPES = ("INT", "FLOAT", "FLOAT", "INT", "STRING", "STRING", "STRING", "INT", "STRING")
    RETURN_NAMES = ("length", "offset_s", "duration_s", "seed", "prompt",
                    "first_still", "last_still", "window_count", "summary")
    FUNCTION = "run"
    CATEGORY = CATEGORY

    @classmethod
    def IS_CHANGED(cls, plan_path, window_id, take=0):
        return f"{_mtime(plan_path)}:{window_id}:{take}"

    def run(self, plan_path, window_id, take=0):
        plan = plan_io.load_plan(plan_path)
        window = plan_io.window_by_id(plan, window_id)
        seed = plan_io.seed_for(window_id, take) if take else int(window.get("seed"))
        return (
            int(window["nframes"]),
            float(window["audio_start_s"]),
            float(window["duration_s"]),
            int(seed),
            str(window.get("prompt_full") or window.get("prompt") or ""),
            str(window.get("first_still") or ""),
            str(window.get("last_still") or ""),
            plan_io.window_count(plan),
            plan_io.summary(plan, window),
        )


class H3EDLStill:
    """Load a window's inject still as an IMAGE, byte-for-byte off disk.

    No resize, no crop, no VAE round-trip: the pixels that land on frame 0 of
    this window are the pixels the previous window was told to end on.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "plan_path": ("STRING", {"default": "", "multiline": False}),
                "window_id": ("INT", {"default": 1, "min": 1, "max": 4096}),
                "which": (["first", "last"], {"default": "first"}),
            },
            "optional": {
                "input_dir": ("STRING", {"default": "", "multiline": False}),
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING", "STRING")
    RETURN_NAMES = ("image", "path", "sha256")
    FUNCTION = "run"
    CATEGORY = CATEGORY

    @classmethod
    def IS_CHANGED(cls, plan_path, window_id, which, input_dir=""):
        return f"{_mtime(plan_path)}:{window_id}:{which}:{input_dir}"

    def run(self, plan_path, window_id, which="first", input_dir=""):
        import numpy as np
        import torch
        from PIL import Image

        plan = plan_io.load_plan(plan_path)
        window = plan_io.window_by_id(plan, window_id)
        name = plan_io.still_name(window, which)
        path = plan_io.resolve_still(name, _comfy_input_dir(input_dir))

        image = Image.open(path)
        image = image.convert("RGB")
        want = (int(plan.get("video", {}).get("width") or 0),
                int(plan.get("video", {}).get("height") or 0))
        if all(want) and image.size != want:
            print(f"[h3_edl_window] {path.name} is {image.size}, plan canvas is {want}. "
                  "MiniMaxH3SeamToVideo will rescale it, so the join will not be "
                  "pixel-identical. Re-export the inject at the plan canvas.")
        array = np.array(image).astype(np.float32) / 255.0
        return (torch.from_numpy(array)[None, ], str(path), plan_io.sha256_file(path))


class H3EDLSeamCheck:
    """Assert two images are the same pixels (window N last vs N+1 first)."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image_a": ("IMAGE",),
                "image_b": ("IMAGE",),
                "on_mismatch": (["error", "warn"], {"default": "error"}),
            },
            "optional": {
                "tolerance": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.001}),
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "report")
    FUNCTION = "run"
    CATEGORY = CATEGORY

    def run(self, image_a, image_b, on_mismatch="error", tolerance=0.0):
        import torch

        if image_a.shape != image_b.shape:
            report = f"seam MISMATCH: shapes {tuple(image_a.shape)} vs {tuple(image_b.shape)}"
            if on_mismatch == "error":
                raise ValueError(report)
            print(f"[h3_edl_window] {report}")
            return (image_a, report)
        delta = float(torch.max(torch.abs(image_a - image_b)).item())
        if delta > tolerance:
            report = f"seam MISMATCH: max abs delta {delta:.6f} > tolerance {tolerance}"
            if on_mismatch == "error":
                raise ValueError(report)
            print(f"[h3_edl_window] {report}")
        else:
            report = f"seam OK: max abs delta {delta:.6f}"
        return (image_a, report)
