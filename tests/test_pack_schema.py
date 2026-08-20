#!/usr/bin/env python
"""Validate catalog packs against docs/SCHEMA.md. No Comfy, no GPU."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))

from from_pack import load_project, project_to_state, shot_duration  # noqa: E402

PACK = ROOT / "catalog" / "01-dont-freak"
CANON_PHRASES = [
    "Did you forgive yourself recently?",
    "Are you taking it easy?",
    "You know it doesn't have to be that way",
    "I know that it's not easy",
    "You know that it's not easy",
    "But you know it doesn't have to be that way",
    "So don't freak",
    "We'll just dance our way out of this one",
    "We'll just dance our way right out of this one",
    "don't you freak",
    "Yeah, Don't freak",
    "We'll dance our way out of this one",
    "Shit might look bad",
    "But we'll dance our way out of this one",
    "yeah we'll dance our way out of this one",
    "The future is cool",
    "But the present sort of sucks",
    "So just don't freak",
    "An' we'll dance our....",
    "Have you forgiven yourself recently?",
]


def _load(name: str):
    return json.loads((PACK / name).read_text(encoding="utf-8"))


class SchemaPackTests(unittest.TestCase):
    def setUp(self):
        self.project = _load("project.json")
        self.lyrics = _load("lyrics.json")
        self.index = json.loads((ROOT / "catalog" / "index.json").read_text(encoding="utf-8"))

    def test_index_lists_dont_freak_as_01(self):
        songs = self.index["songs"]
        self.assertEqual(songs[0]["id"], "01-dont-freak")
        self.assertEqual(songs[0]["number"], 1)
        self.assertTrue((ROOT / songs[0]["pack"] / "project.json").is_file())

    def test_project_schema_v1(self):
        self.assertEqual(self.project["project_schema"], 1)
        for key in ("project", "song", "song_duration_s", "bpm", "style_block",
                    "settings", "characters", "shots"):
            self.assertIn(key, self.project)
        self.assertGreaterEqual(len(self.project["characters"]), 1)
        self.assertGreaterEqual(len(self.project["shots"]), 1)

    def test_settings_native_canvas(self):
        s = self.project["settings"]
        self.assertEqual(s["width"], 1344)
        self.assertEqual(s["height"], 768)

    def test_start_s_drives_duration(self):
        shots = self.project["shots"]
        song_end = self.project["song_duration_s"]
        starts = [shot["start_s"] for shot in shots]
        self.assertEqual(starts, sorted(starts))
        self.assertEqual(starts[0], 0.0)
        for i, shot in enumerate(shots):
            dur = shot_duration(shots, i, song_end)
            self.assertGreaterEqual(dur, 5.0 - 1e-6)
            self.assertLessEqual(dur, 15.0 + 1e-6)

    def test_pack_refs_are_schema_relative(self):
        for shot in self.project["shots"]:
            for ref in shot.get("refs") or []:
                self.assertTrue(
                    ref.startswith("assets/"),
                    f"{shot['name']} ref {ref} should be pack-relative",
                )

    def test_audio_mode_per_shot(self):
        for shot in self.project["shots"]:
            self.assertIn(shot["audio_mode"], ("raw", "pulse"))
            self.assertEqual(shot["audio_mode"], "raw")

    def test_lyrics_are_object_list_not_string(self):
        self.assertIsInstance(self.lyrics, list)
        self.assertIsInstance(self.project["lyrics"], list)
        self.assertNotIsInstance(self.lyrics, str)
        self.assertEqual(self.lyrics, self.project["lyrics"])
        prev_end = -1.0
        for line in self.lyrics:
            self.assertIsInstance(line, dict)
            self.assertIsInstance(line["text"], str)
            self.assertIsInstance(line["start"], (int, float))
            self.assertIsInstance(line["end"], (int, float))
            self.assertLess(line["start"], line["end"])
            self.assertGreaterEqual(line["start"], prev_end - 1e-6)
            prev_end = line["end"]
            self.assertNotIn("\n", line["text"])

    def test_lyrics_quote_canon_only(self):
        texts = [line["text"] for line in self.lyrics]
        for phrase in CANON_PHRASES:
            self.assertIn(phrase, texts, f"missing canon line: {phrase}")
        allowed = set(CANON_PHRASES) | {
            "don't freak",
            "Don't freak",
            "this one",
        }
        for text in texts:
            self.assertIn(text, allowed, f"invented lyric: {text}")

    def test_locations_marked_empty(self):
        locs = self.project["locations"]
        self.assertTrue(locs)
        for loc in locs:
            self.assertTrue(loc["empty"])
            self.assertIn("empty", loc["name"])

    def test_overlays_not_in_prompts(self):
        prompts = " ".join(shot["prompt"] for shot in self.project["shots"])
        self.assertNotIn("r u ok?", prompts)
        self.assertNotIn("its cool man", prompts)
        overlays = _load("overlays.json")
        self.assertTrue(overlays["after_concat"])
        self.assertTrue(overlays["never_in_h3_prompt"])
        im_texts = {row["text"] for row in overlays["im"]}
        self.assertEqual(im_texts, {"r u ok?", "its cool man"})

    def test_prompts_forbid_generated_text(self):
        for shot in self.project["shots"]:
            low = shot["prompt"].lower()
            self.assertTrue(
                "no on-screen text" in low
                or "no burned-in lyrics" in low
                or "do not write any words" in low
                or "no im" in low,
                msg=shot["name"],
            )

    def test_cats_only_from_135(self):
        for shot in self.project["shots"]:
            if "CHAR_CATS" in (shot.get("characters") or []):
                self.assertGreaterEqual(shot["start_s"], 95.0, shot["name"])

    def test_cat_recast_is_gowned_pair(self):
        cats = next(c for c in self.project["characters"] if c["id"] == "CHAR_CATS")
        desc = cats["description"].lower()
        self.assertIn("evening gown", desc)
        self.assertIn("always a pair", desc)
        self.assertIn("do not regenerate", desc)
        self.assertEqual(cats["behem"], "C:/Users/adaml/dont-freak-refs/06-cat-violins.png")
        retired = ("pink inner", "chest stitch", "standing on a rug", "in nothing")
        blob = json.dumps(self.project).lower()
        for phrase in retired:
            self.assertNotIn(phrase, blob)
        enter = next(s for s in self.project["shots"] if s["id"] == 10)
        self.assertIn("evening gown", enter["prompt"].lower())
        self.assertIn("do not regenerate cat faces", enter["prompt"].lower())

    def test_quill_is_late(self):
        reveal = [s for s in self.project["shots"] if "quill letter" in s["prompt"].lower()]
        self.assertTrue(reveal)
        for shot in reveal:
            self.assertGreaterEqual(shot["start_s"], 178.0)
        early = [s for s in self.project["shots"] if s["start_s"] < 178.0]
        for shot in early:
            self.assertNotIn("quill letter", shot["prompt"].lower())

    def test_lyric_cu_shots_are_sloth_only(self):
        for shot in self.project["shots"]:
            if shot["name"].endswith("lyric CU") or shot["name"].startswith("verse 1"):
                self.assertEqual(shot["characters"], ["CHAR_SLOTH"], shot["name"])
                self.assertEqual(shot["audio_mode"], "raw")
                self.assertIn("ONLY the sloth", shot["prompt"])

    def test_style_block_bans_onscreen_text(self):
        self.assertIn("No on-screen text", self.project["style_block"])
        self.assertIn("Never humans", self.project["style_block"])

    def test_from_pack_maps_sheets_to_comfy_input(self):
        state = project_to_state(self.project, cfg={})
        flat = [ref for chunk in state["chunks"] for ref in chunk["refs"]]
        self.assertTrue(any(ref.startswith("dont_freak/") for ref in flat))
        self.assertFalse(any(ref.startswith("assets/") for ref in flat))

    def test_from_pack_state_is_consumable(self):
        loaded = load_project(PACK)
        state = project_to_state(loaded, cfg={})
        self.assertEqual(len(state["chunks"]), 20)
        self.assertEqual(state["slug"], "dont_freak")
        self.assertEqual(state["song"]["duration_s"], 211)
        total = sum(c["duration_s"] for c in state["chunks"])
        self.assertAlmostEqual(total, 211.0, places=3)
        for chunk in state["chunks"]:
            for key in ("id", "name", "offset_s", "duration_s", "first_frame",
                        "refs", "prompt", "audio_mode", "status"):
                self.assertIn(key, chunk)
            self.assertEqual(chunk["audio_mode"], "raw")
            self.assertEqual(chunk["status"], "pending")

    def test_checked_in_state_example_matches_from_pack(self):
        state = _load("state.example.json")
        rebuilt = project_to_state(self.project, cfg={})
        self.assertEqual(
            [(c["id"], c["offset_s"], c["duration_s"], c["audio_mode"]) for c in state["chunks"]],
            [(c["id"], c["offset_s"], c["duration_s"], c["audio_mode"]) for c in rebuilt["chunks"]],
        )


if __name__ == "__main__":
    unittest.main()
