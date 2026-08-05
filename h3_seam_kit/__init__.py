"""h3_seam_kit — custom MiniMax H3 nodes for the BUSY music-video pipeline.

MiniMaxH3SeamToVideo : pinned first/last frames (keyframes) + pack refs + song
    audio ref in ONE conditioning pass. Fixes the stock nodes' either/or by
    merging minimax_keyframes + minimax_refs (model_base patched to merge
    cond_video_latents). Seam frames are NOT tagged in the tokenizer, so
    <Picture N> tags map 1:1 to the pack refs as the prompts expect.
BeatPulse           : song window -> rhythm-only pulse track (onsets -> synth
    hits). The model gets the beat without vocals, so motion syncs and nothing
    lip-syncs.
SongWindow          : crop an audio window + its beat grid.
SeamFrame           : pull the exact last/first frame of a video file.
BeatSnapDuration    : snap a desired duration to the beat grid.
PromptDoctor        : assemble the final prompt from parts.
"""
import json
import os
import subprocess

import numpy as np
import torch
import torchaudio

import comfy.model_management
import comfy.utils
import node_helpers
from PIL import Image

CANVAS_MULTIPLE = 32
BASE_SHORT_EDGE = 768
MAX_PIXELS = 768 * 1344
REF_IMAGE_SHORT_EDGE = 2048
FPS = 24
AUDIO_LATENT_FPS = 40
VAE_SR = 32000
FFMPEG = r"C:/Users/adaml/AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-8.1.2-full_build/bin/ffmpeg.exe"


def _align_frame_count(n):
    while n % 17 != 5:
        n += 1
    return n


def _video_latent_t(frame_count):
    return 2 if frame_count <= 5 else ((frame_count - 5) // 17) * 5 + 2


def _temporal_shape(length):
    frame_count = _align_frame_count(max(5, length))
    duration = frame_count / FPS
    return frame_count, _video_latent_t(frame_count), round(duration * AUDIO_LATENT_FPS)


def _adapt_canvas(width, height):
    ratio = width / height
    if ratio >= 1.0:
        nom_w, nom_h = BASE_SHORT_EDGE * ratio, BASE_SHORT_EDGE
    else:
        nom_w, nom_h = BASE_SHORT_EDGE, BASE_SHORT_EDGE / ratio
    if nom_w * nom_h > MAX_PIXELS:
        s = (MAX_PIXELS / (nom_w * nom_h)) ** 0.5
        nom_w, nom_h = nom_w * s, nom_h * s
    return (max(CANVAS_MULTIPLE, round(nom_w / CANVAS_MULTIPLE) * CANVAS_MULTIPLE),
            max(CANVAS_MULTIPLE, round(nom_h / CANVAS_MULTIPLE) * CANVAS_MULTIPLE))


def _resize(image, width, height, crop):
    samples = image[..., :3].movedim(-1, 1)
    samples = comfy.utils.common_upscale(samples, width, height, "lanczos", crop)
    return samples.movedim(1, -1)


def _empty_av_latent(width, height, length, batch_size=1):
    frame_count, latent_t, audio_t = _temporal_shape(length)
    video = torch.zeros([batch_size, 24, latent_t, height // 16, width // 16],
                        device=comfy.model_management.intermediate_device())
    audio = torch.zeros([batch_size, 32, 2, audio_t],
                        device=comfy.model_management.intermediate_device())
    return {"samples": comfy.nested_tensor.NestedTensor((video, audio))}, frame_count


def _audio_vae_encode(audio_vae, audio):
    waveform = audio["waveform"]
    sr = audio["sample_rate"]
    vae_sr = getattr(audio_vae, "audio_sample_rate", VAE_SR)
    if sr != vae_sr:
        waveform = torchaudio.functional.resample(waveform, sr, vae_sr)
    z = audio_vae.encode(waveform[:1].movedim(1, -1))
    return z, z.shape[-1]


class MiniMaxH3SeamToVideo:
    """Pinned first/last keyframes + reference images + reference audio, one pass."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "clip": ("CLIP",),
                "vae": ("VAE",),
                "audio_vae": ("VAE",),
                "prompt": ("STRING", {"multiline": True}),
                "width": ("INT", {"default": 1344, "min": 32, "max": 8192, "step": 32}),
                "height": ("INT", {"default": 768, "min": 32, "max": 8192, "step": 32}),
                "length": ("INT", {"default": 124, "min": 5, "max": 3600, "step": 17}),
                "ref_image_size": (["match", "max"], {"default": "match"}),
            },
            "optional": {
                "first_frame": ("IMAGE",),
                "last_frame": ("IMAGE",),
                "ref_image_1": ("IMAGE",),
                "ref_image_2": ("IMAGE",),
                "ref_image_3": ("IMAGE",),
                "ref_image_4": ("IMAGE",),
                "ref_audio_1": ("AUDIO",),
            },
        }

    RETURN_TYPES = ("CONDITIONING", "LATENT")
    RETURN_NAMES = ("positive", "latent")
    FUNCTION = "run"
    CATEGORY = "model/conditioning/minimax"

    def run(self, clip, vae, audio_vae, prompt, width, height, length,
            ref_image_size="match", first_frame=None, last_frame=None,
            ref_image_1=None, ref_image_2=None, ref_image_3=None, ref_image_4=None,
            ref_audio_1=None):
        latent, frame_count = _empty_av_latent(width, height, length)

        # --- pinned keyframes (conditioning channel, NOT tokenizer-tagged) ---
        keyframes = []
        if first_frame is not None:
            img = _resize(first_frame[:1], width, height, "disabled")
            keyframes.append({"resolved_frame_index": 0, "image": img,
                              "latent": vae.encode(img)})
        if last_frame is not None:
            img = _resize(last_frame[:1], width, height, "center")
            keyframes.append({"resolved_frame_index": frame_count - 1, "image": img,
                              "latent": vae.encode(img)})

        # --- reference images + audio (tokenizer-tagged: <Picture N> / <Audio 1>) ---
        ref_images = [im for im in (ref_image_1, ref_image_2, ref_image_3, ref_image_4)
                      if im is not None]
        ref_items = []
        ref_blocks = []
        for img in ref_images:
            h, w = img.shape[1], img.shape[2]
            if ref_image_size == "match":
                scale = min(1.0, ((width * height) / (w * h)) ** 0.5)
            else:
                scale = min(1.0, REF_IMAGE_SHORT_EDGE / min(w, h))
            tw = max(CANVAS_MULTIPLE, round(w * scale / CANVAS_MULTIPLE) * CANVAS_MULTIPLE)
            th = max(CANVAS_MULTIPLE, round(h * scale / CANVAS_MULTIPLE) * CANVAS_MULTIPLE)
            resized = _resize(img[:1], tw, th, "disabled")
            z = vae.encode(resized)
            ref_items.append({"type": "image", "data": resized})
            ref_blocks.append({"kind": "image", "latent_h": th // 16, "latent_w": tw // 16,
                               "latent": z})

        if ref_audio_1 is not None:
            audio_latent, ref_audio_t = _audio_vae_encode(audio_vae, ref_audio_1)
            ref_items.append({"type": "audio"})
            ref_blocks.append({"kind": "audio", "ref_audio_t": ref_audio_t,
                               "audio_latent": audio_latent})

        tokens = clip.tokenize(prompt, minimax_ref_items=ref_items)
        cond = clip.encode_from_tokens_scheduled(tokens)

        if keyframes:
            cond = node_helpers.conditioning_set_values(cond, {
                "minimax_keyframes": keyframes,
                "minimax_frame_count": frame_count,
            })
        if ref_blocks:
            cond = node_helpers.conditioning_set_values(cond, {"minimax_refs": ref_blocks})
        return (cond, latent)


class BeatPulse:
    """Song window -> rhythm-only pulse track: onset hits at the song's beat
    positions. The model gets rhythm without vocals (no lip-sync)."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("AUDIO",),
                "pulse_type": (["kick", "click", "shaker"], {"default": "kick"}),
                "gain": ("FLOAT", {"default": 1.0, "min": 0.1, "max": 3.0, "step": 0.05}),
            }
        }

    RETURN_TYPES = ("AUDIO", "INT", "STRING")
    RETURN_NAMES = ("pulse", "beat_count", "beat_times_json")
    FUNCTION = "run"
    CATEGORY = "audio"

    def run(self, audio, pulse_type="kick", gain=1.0):
        import librosa
        waveform = audio["waveform"]  # [B, C, L]
        sr = int(audio["sample_rate"])
        y = waveform[0, 0].detach().cpu().numpy().astype(np.float32)
        onsets = librosa.onset.onset_detect(y=y, sr=sr, backtrack=True)
        times = librosa.frames_to_time(onsets, sr=sr)

        n = y.shape[0]
        pulse = np.zeros(n, dtype=np.float32)
        sr_f = float(sr)
        if pulse_type == "kick":
            dur = int(0.12 * sr_f)
            t = np.arange(dur) / sr_f
            hit = np.sin(2 * np.pi * 95 * t) * np.exp(-t * 38)
        elif pulse_type == "click":
            dur = int(0.03 * sr_f)
            t = np.arange(dur) / sr_f
            hit = np.random.RandomState(0).randn(dur) * np.exp(-t * 160)
        else:  # shaker
            dur = int(0.08 * sr_f)
            t = np.arange(dur) / sr_f
            hit = np.random.RandomState(1).randn(dur) * np.exp(-t * 70)
        hit = hit / (np.abs(hit).max() + 1e-8)
        for tm in times:
            i = int(round(tm * sr_f))
            if 0 <= i < n:
                j = min(dur, n - i)
                pulse[i:i + j] += hit[:j] * gain
        peak = np.abs(pulse).max() + 1e-8
        pulse = pulse / peak * 0.9
        out = torch.from_numpy(pulse).float().unsqueeze(0).unsqueeze(0)
        return ({"waveform": out, "sample_rate": sr}, int(len(times)),
                json.dumps([round(float(t), 3) for t in times]))


class SongWindow:
    """Crop an audio window from a loaded track + its relative beat grid."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("AUDIO",),
                "offset_s": ("FLOAT", {"default": 0.0, "min": 0.0}),
                "duration_s": ("FLOAT", {"default": 14.0, "min": 3.0, "max": 20.0}),
            }
        }

    RETURN_TYPES = ("AUDIO", "INT", "STRING")
    RETURN_NAMES = ("window", "beat_count", "beat_times_json")
    FUNCTION = "run"
    CATEGORY = "audio"

    def run(self, audio, offset_s, duration_s):
        import librosa
        waveform = audio["waveform"]
        sr = int(audio["sample_rate"])
        start = int(round(offset_s * sr))
        end = min(waveform.shape[-1], int(round((offset_s + duration_s) * sr)))
        crop = waveform[..., start:end]
        y = crop[0, 0].detach().cpu().numpy().astype(np.float32)
        onsets = librosa.onset.onset_detect(y=y, sr=sr, backtrack=True)
        times = librosa.frames_to_time(onsets, sr=sr)
        return ({"waveform": crop, "sample_rate": sr}, int(len(times)),
                json.dumps([round(float(t), 3) for t in times]))


class SeamFrame:
    """Pull the exact last (or first) frame of a video file as an IMAGE."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video_path": ("STRING", {"default": ""}),
                "mode": (["last", "first"], {"default": "last"}),
            }
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "run"
    CATEGORY = "video"

    def run(self, video_path, mode="last"):
        import io as _io
        if not os.path.isfile(video_path):
            raise ValueError(f"video not found: {video_path}")
        args = [FFMPEG, "-y"]
        if mode == "last":
            args += ["-sseof", "-0.05"]
        else:
            args += ["-ss", "0"]
        args += ["-i", video_path, "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-"]
        r = subprocess.run(args, capture_output=True, timeout=60)
        if r.returncode != 0 or not r.stdout:
            raise ValueError(f"SeamFrame failed: {r.stderr.decode(errors='replace')[-200:]}")
        img = Image.open(_io.BytesIO(r.stdout)).convert("RGB")
        tensor = torch.from_numpy(np.array(img).astype(np.float32) / 255.0).unsqueeze(0)
        return (tensor,)


class BeatSnapDuration:
    """Snap a desired shot length onto the beat grid (bpm), clamped [min,max]."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "desired_s": ("FLOAT", {"default": 14.0, "min": 3.0, "max": 20.0}),
                "bpm": ("FLOAT", {"default": 172.3, "min": 40.0, "max": 240.0}),
                "min_s": ("FLOAT", {"default": 5.0, "min": 3.0, "max": 15.0}),
                "max_s": ("FLOAT", {"default": 15.0, "min": 5.0, "max": 20.0}),
            }
        }

    RETURN_TYPES = ("FLOAT", "INT")
    RETURN_NAMES = ("duration_s", "beat_count")
    FUNCTION = "run"
    CATEGORY = "audio"

    def run(self, desired_s, bpm, min_s, max_s):
        beats = max(1, int(round(desired_s * bpm / 60.0)))
        dur = beats * 60.0 / bpm
        dur = max(min_s, min(max_s, dur))
        beats = max(1, int(round(dur * bpm / 60.0)))
        return (round(dur, 3), beats)


class PromptDoctor:
    """Assemble the final generation prompt from parts, consistently."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "shot": ("STRING", {"multiline": True}),
                "style": ("STRING", {"multiline": True, "default": ""}),
                "panel_note": ("STRING", {"multiline": True, "default": ""}),
            },
            "optional": {
                "audio_note": ("STRING", {"multiline": True, "default": ""}),
                "beat_count": ("INT", {"default": 0}),
                "anti_lipsync": ("BOOLEAN", {"default": True}),
            },
        }

    RETURN_TYPES = ("STRING",)
    FUNCTION = "run"
    CATEGORY = "text"

    def run(self, shot, style, panel_note, audio_note="", beat_count=0, anti_lipsync=True):
        parts = [shot]
        if panel_note:
            parts.append(panel_note)
        if beat_count and beat_count > 0:
            parts.append(f"This shot spans {beat_count} beats of the music.")
        if anti_lipsync:
            parts.append("No lip-sync: characters never mouth or sing the words; keep mouths neutral and closed.")
        if audio_note:
            parts.append(audio_note)
        if style:
            parts.append(style)
        return (" ".join(p for p in parts if p).strip(),)


NODE_CLASS_MAPPINGS = {
    "MiniMaxH3SeamToVideo": MiniMaxH3SeamToVideo,
    "BeatPulse": BeatPulse,
    "SongWindow": SongWindow,
    "SeamFrame": SeamFrame,
    "BeatSnapDuration": BeatSnapDuration,
    "PromptDoctor": PromptDoctor,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MiniMaxH3SeamToVideo": "MiniMax H3 Seam to Video",
    "BeatPulse": "Beat Pulse (anti-lipsync)",
    "SongWindow": "Song Window",
    "SeamFrame": "Seam Frame",
    "BeatSnapDuration": "Beat Snap Duration",
    "PromptDoctor": "Prompt Doctor",
}
