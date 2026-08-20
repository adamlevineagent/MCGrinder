"""h3_edl_window — drive MiniMax H3 windows from a frame EDL.

A NEW package. It does not replace, extend or vendor `h3_seam_kit`; it feeds
it. Copy this folder to `ComfyUI/custom_nodes/h3_edl_window/` and leave the
live `ComfyUI/custom_nodes/h3_seam_kit/` alone.

Plans come from `pipeline/plan_windows.py` in the MCGrinder repo.
"""
from .nodes import H3EDLSeamCheck, H3EDLStill, H3EDLWindow

NODE_CLASS_MAPPINGS = {
    "H3EDLWindow": H3EDLWindow,
    "H3EDLStill": H3EDLStill,
    "H3EDLSeamCheck": H3EDLSeamCheck,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "H3EDLWindow": "H3 EDL Window",
    "H3EDLStill": "H3 EDL Still (inject frame)",
    "H3EDLSeamCheck": "H3 EDL Seam Check",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
