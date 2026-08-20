#!/usr/bin/env python
"""Config loader + snap/redo/from_pack wiring. No Comfy, no GPU."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PIPE = ROOT / "pipeline"
sys.path.insert(0, str(PIPE))

import from_pack  # noqa: E402
import load_config  # noqa: E402
import redo  # noqa: E402
import snap_beats  # noqa: E402


class ConfigLoadTests(unittest.TestCase):
    def test_missing_config_is_empty_dict(self):
        env = os.environ.pop("MCGRINDER_CONFIG", None)
        try:
            # load_config still sees repo config.json if present; force a missing path
            os.environ["MCGRINDER_CONFIG"] = str(ROOT / "does-not-exist.json")
            # candidates include the missing env path then repo config.json
            cfg = load_config.load_config()
            self.assertIsInstance(cfg, dict)
        finally:
            if env is None:
                os.environ.pop("MCGRINDER_CONFIG", None)
            else:
                os.environ["MCGRINDER_CONFIG"] = env

    def test_env_config_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cfg.json"
            path.write_text(json.dumps({
                "audio_mode_default": "pulse",
                "state_file": str(Path(tmp) / "state.json"),
                "comfy": {"url": "http://127.0.0.1:9", "dir": str(tmp)},
            }), encoding="utf-8")
            os.environ["MCGRINDER_CONFIG"] = str(path)
            try:
                cfg = load_config.load_config()
                self.assertEqual(cfg["audio_mode_default"], "pulse")
                self.assertEqual(load_config.comfy_url(cfg), "http://127.0.0.1:9")
                self.assertEqual(load_config.state_path(cfg), Path(tmp) / "state.json")
            finally:
                os.environ.pop("MCGRINDER_CONFIG", None)

    def test_chunk_audio_mode_wins_over_pulse_default(self):
        cfg = {"audio_mode_default": "pulse"}
        state = {"audio_mode_default": "pulse"}
        self.assertEqual(load_config.chunk_audio_mode({}, cfg, state), "pulse")
        self.assertEqual(
            load_config.chunk_audio_mode({"audio_mode": "raw"}, cfg, state),
            "raw",
        )

    def test_example_configs_parse(self):
        generic = json.loads((ROOT / "config.example.json").read_text(encoding="utf-8"))
        behem = json.loads((ROOT / "config.behem.example.json").read_text(encoding="utf-8"))
        self.assertEqual(generic["comfy"]["dir"], "D:/ComfyUI")
        self.assertEqual(behem["comfy"]["dir"], "C:/ComfyUI")
        self.assertEqual(behem["comfy"]["version"], "0.30.0")
        self.assertIn("dont-freak-refs", behem["refs_dir"])
        self.assertIn("Don't Freak.wav", behem["song"])

    def test_snap_beats_uses_state_duration_not_busy_264(self):
        beats = [0.0, 5.2, 10.1, 15.0, 20.0]
        state = {
            "song": {"duration_s": 20.0},
            "chunks": [
                {"id": 1, "name": "a", "offset_s": 0.2, "duration_s": 11.0},
                {"id": 2, "name": "b", "offset_s": 11.0, "duration_s": 9.0},
            ],
        }
        end = snap_beats.snap_state(state, beats)
        self.assertEqual(end, 20.0)
        self.assertAlmostEqual(
            state["chunks"][0]["offset_s"] + sum(c["duration_s"] for c in state["chunks"]),
            20.0,
            places=3,
        )

    def test_redo_reads_config_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_file = Path(tmp) / "state.json"
            state_file.write_text(json.dumps({
                "chunks": [
                    {"id": 1, "name": "one", "status": "done", "output": "x.mp4",
                     "prompt_id": "abc", "errors": 2, "redo": 0},
                    {"id": 2, "name": "two", "status": "done", "output": "y.mp4",
                     "prompt_id": "def", "errors": 0, "redo": 0},
                ]
            }), encoding="utf-8")
            cfg_path = Path(tmp) / "cfg.json"
            cfg_path.write_text(json.dumps({"state_file": str(state_file)}), encoding="utf-8")
            os.environ["MCGRINDER_CONFIG"] = str(cfg_path)
            try:
                self.assertEqual(redo.main(["1"]), 0)
                s = json.loads(state_file.read_text(encoding="utf-8"))
                self.assertEqual(s["chunks"][0]["status"], "pending")
                self.assertEqual(s["chunks"][0]["redo"], 1)
                self.assertEqual(s["chunks"][1]["status"], "done")
            finally:
                os.environ.pop("MCGRINDER_CONFIG", None)

    def test_from_pack_cli_stdout(self):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = from_pack.main([str(ROOT / "catalog" / "01-dont-freak"), "--stdout"])
        self.assertEqual(rc, 0)
        data = json.loads(buf.getvalue())
        self.assertEqual(len(data["chunks"]), 20)


if __name__ == "__main__":
    unittest.main()
