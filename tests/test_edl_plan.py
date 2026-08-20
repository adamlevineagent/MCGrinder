#!/usr/bin/env python
"""Frame EDL + window planner + h3_edl_window node pack. No Comfy, no GPU."""
from __future__ import annotations

import ast
import json
import struct
import sys
import tempfile
import unittest
import wave
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pipeline"))

import plan_windows  # noqa: E402
from comfy_nodes.h3_edl_window import (  # noqa: E402
    NODE_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS,
    plan_io,
)
from from_pack import load_project  # noqa: E402

PACK = ROOT / "catalog" / "01-dont-freak"
AUDIO_INPUT = "dont_freak/Don't Freak.wav"
FL2V_TURBO = "minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors"
REF2V_TURBO = "minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors"


def png_bytes(width=8, height=8, rgb=(200, 30, 30)) -> bytes:
    """A real, tiny PNG so tests never need PIL to make fixtures."""
    raw = b"".join(b"\x00" + bytes(rgb) * width for _ in range(height))

    def chunk(tag, data):
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw))
            + chunk(b"IEND", b""))


def write_wav(path, seconds=2.5, sample_rate=48000, channels=2):
    frames = int(seconds * sample_rate)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(b"\x00\x00" * channels * frames)
    return frames


def synthetic_edl(hits, duration_s=30.0, **defaults):
    """hits: list of (t_sec, kind). Every row shares one plate still."""
    rows = []
    for i, (t_sec, kind) in enumerate(hits, start=1):
        rows.append({"id": i, "text": f"hit {i}", "t_sec": t_sec,
                     "frame_24": plan_windows.frame_for(t_sec), "kind": kind,
                     "still": "PLATE", "refs": [], "camera": "locked", "shot": None})
    rows.append({"id": len(rows) + 1, "text": "end", "t_sec": duration_s,
                 "frame_24": plan_windows.frame_for(duration_s), "kind": "end",
                 "still": "PLATE", "refs": [], "camera": "locked", "shot": None})
    return {
        "edl_schema": 1, "project": "synthetic", "slug": "synth", "fps": 24,
        "video": {"width": 1344, "height": 768},
        "audio": {"sample_rate": 48000, "duration_s": duration_s,
                  "total_samples": int(duration_s * 48000),
                  "frames_24": plan_windows.frame_for(duration_s)},
        "model": {"turbo_lora": FL2V_TURBO, "steps": 8},
        "defaults": dict({"camera": "locked", "audio_mode": "raw", "fit": "cover",
                          "min_fill_frames": 124}, **defaults),
        "stills": [{"id": "PLATE", "name": "plate", "role": "inject",
                    "body": "empty_plate", "status": "on_behem",
                    "comfy_input": "synth/plate.png"}],
        "rows": rows,
    }


class EdlFileTests(unittest.TestCase):
    def setUp(self):
        self.edl = plan_windows.load_edl(PACK)
        self.project = load_project(PACK)
        self.stills = plan_windows.still_index(self.edl)

    def test_edl_validates_clean(self):
        self.assertEqual(plan_windows.validate_edl(self.edl, self.project), [])

    def test_frames_are_round_t_times_24(self):
        prev = -1
        for row in self.edl["rows"]:
            self.assertEqual(row["frame_24"], round(row["t_sec"] * 24), row["text"])
            self.assertGreater(row["frame_24"], prev, row["text"])
            prev = row["frame_24"]
        self.assertEqual(self.edl["rows"][0]["frame_24"], 0)
        self.assertEqual(self.edl["rows"][-1]["frame_24"], 5076)
        self.assertEqual(self.edl["rows"][-1]["kind"], "end")

    def test_rows_ride_the_catalog_timeline(self):
        """No parallel timeline: rows are the pack's 20 shots plus the end."""
        starts = [shot["start_s"] for shot in self.project["shots"]]
        row_shots = [row["shot"] for row in self.edl["rows"] if row["kind"] != "end"]
        self.assertEqual(row_shots, [shot["id"] for shot in self.project["shots"]])
        self.assertEqual([row["t_sec"] for row in self.edl["rows"] if row["kind"] != "end"],
                         starts)
        self.assertEqual(starts, [0, 11, 22, 34, 46, 55, 64, 74, 82, 95,
                                  106, 115, 120, 131, 146, 153, 165, 178, 190, 200])

    def test_audio_block_matches_the_behem_probe(self):
        audio = self.edl["audio"]
        self.assertEqual(audio["codec"], "pcm_s16le")
        self.assertEqual(audio["sample_rate"], 48000)
        self.assertEqual(audio["channels"], 2)
        self.assertEqual(audio["duration_s"], 211.479979)
        self.assertEqual(audio["frames_24"], 5076)
        self.assertEqual(audio["frames_24"], round(audio["duration_s"] * 24))

    def test_no_cut_frame_is_a_bust_or_a_collage(self):
        for row in self.edl["rows"]:
            still = self.stills[row["still"]]
            self.assertEqual(still["role"], "inject", row["text"])
            self.assertIn(still["body"], plan_windows.INJECT_BODIES, row["text"])

    def test_band_bible_collage_is_declared_and_unused(self):
        bible = self.stills["BAND_BIBLE_COLLAGE"]
        self.assertEqual(bible["role"], "forbidden")
        self.assertEqual(bible["body"], "collage")
        self.assertTrue(bible["never_inject"])
        blob = json.dumps(self.edl["rows"])
        self.assertNotIn("BAND_BIBLE_COLLAGE", blob)
        self.assertNotIn("00-band-bible", blob)

    def test_identity_sheets_stay_refs(self):
        for ref_id in ("REF_SLOTH", "REF_GRIZZLY", "REF_LAB", "REF_CATS"):
            still = self.stills[ref_id]
            self.assertEqual(still["role"], "identity_ref")
            self.assertTrue(still["never_inject"])
            self.assertNotIn(ref_id, json.dumps(self.edl["rows"]))

    def test_every_performer_inject_stands_on_the_floor(self):
        for still in self.edl["stills"]:
            if still["role"] != "inject" or still["body"] != "standing_full":
                continue
            brief = still["brief"].lower()
            self.assertIn("full-bleed", brief, still["id"])
            self.assertTrue("feet on" in brief or "meets the floor" in brief, still["id"])

    def test_turbo_lora_is_the_fl2v_window_lora(self):
        model = self.edl["model"]
        self.assertEqual(model["turbo_lora"], FL2V_TURBO)
        self.assertEqual(model["steps"], 8)
        self.assertEqual(model["do_not_mix_with"], REF2V_TURBO)
        self.assertNotEqual(model["turbo_lora"], model["do_not_mix_with"])

    def test_catalog_index_points_at_the_edl(self):
        index = json.loads((ROOT / "catalog" / "index.json").read_text(encoding="utf-8"))
        song = index["songs"][0]
        self.assertEqual(song["edl"], "catalog/01-dont-freak/edl.json")
        self.assertTrue((ROOT / song["edl"]).is_file())


class PlannerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.edl = plan_windows.load_edl(PACK)
        cls.project = load_project(PACK)
        cls.plan = plan_windows.plan_from_edl(cls.edl, cls.project, audio_input=AUDIO_INPUT)

    def test_every_window_is_on_the_lattice(self):
        self.assertTrue(self.plan["windows"])
        for window in self.plan["windows"]:
            self.assertIn(window["nframes"], plan_windows.LATTICE, window["name"])
            self.assertEqual(window["nframes"] % 17, 5, window["name"])

    def test_windows_roll_first_frame_onto_last_frame(self):
        windows = self.plan["windows"]
        for before, after in zip(windows, windows[1:]):
            self.assertEqual(before["end_frame"], after["start_frame"])
            self.assertEqual(before["last_still_id"], after["first_still_id"])
            self.assertEqual(before["last_still"], after["first_still"])

    def test_windows_cover_the_whole_song(self):
        windows = self.plan["windows"]
        self.assertEqual(windows[0]["start_frame"], 0)
        self.assertEqual(windows[-1]["end_frame"], 5076)
        self.assertEqual(self.plan["totals"]["timeline_frames"], 5076)

    def test_window_edges_are_edl_frames(self):
        frames = {row["frame_24"] for row in self.edl["rows"]}
        for window in self.plan["windows"]:
            self.assertIn(window["start_frame"], frames)
            self.assertIn(window["end_frame"], frames)

    def test_audio_is_sample_accurate_and_never_past_the_song(self):
        audio = self.edl["audio"]
        for window in self.plan["windows"]:
            self.assertLessEqual(window["audio_end_s"], audio["duration_s"] + 1e-9,
                                 window["name"])
            self.assertLessEqual(window["audio_end_sample"], audio["total_samples"])
            self.assertEqual(window["audio_start_sample"],
                             window["start_frame"] * audio["sample_rate"] // 24)
            self.assertAlmostEqual(window["duration_s"], window["nframes"] / 24, places=6)
            self.assertEqual(window["audio_mode"], "raw")

    def test_the_only_smash_gets_no_window_and_hides_inside_one(self):
        smashes = self.plan["smash_cuts"]
        self.assertEqual(len(smashes), 1)
        smash = smashes[0]
        self.assertEqual((smash["row"], smash["frame_24"], smash["t_sec"]), (12, 2760, 115.0))
        self.assertFalse(smash["auto_demoted"])
        edges = {w["start_frame"] for w in self.plan["windows"]}
        edges |= {w["end_frame"] for w in self.plan["windows"]}
        self.assertNotIn(2760, edges)
        host = plan_io.window_by_id(self.plan, smash["inside_window"])
        self.assertLess(host["start_frame"], 2760)
        self.assertGreater(host["end_frame"], 2760)
        self.assertEqual(host["smash_rows"], [12])
        self.assertEqual((host["start_frame"], host["end_frame"]), (2544, 2880))

    def test_a_hold_row_is_what_lets_a_window_span_a_smash(self):
        rows = {row["id"]: row for row in self.edl["rows"]}
        self.assertEqual(rows[11]["kind"], "hold")
        self.assertEqual(rows[12]["kind"], "smash")
        self.assertEqual(rows[13]["frame_24"] - rows[12]["frame_24"], 120)
        self.assertLess(rows[13]["frame_24"] - rows[12]["frame_24"],
                        self.edl["defaults"]["min_fill_frames"])

    def test_cover_fit_trims_and_never_freezes(self):
        for window in self.plan["windows"]:
            self.assertGreaterEqual(window["trim_tail_frames"], 0)
            if window["hold_tail_frames"]:
                self.assertTrue(window["clamped_by_song_end"], window["name"])
            self.assertEqual(window["trim_tail_frames"] - window["hold_tail_frames"],
                             window["nframes"] - 1 - window["span_frames"])

    def test_last_window_stops_at_the_wav_instead_of_overrunning_it(self):
        last = self.plan["windows"][-1]
        self.assertTrue(last["clamped_by_song_end"])
        self.assertEqual(last["nframes"], 243)
        self.assertEqual(last["hold_tail_frames"], 34)
        self.assertLess(last["audio_end_s"], self.edl["audio"]["duration_s"])

    def test_under_fit_holds_instead_of_trimming(self):
        plan = plan_windows.plan_from_edl(self.edl, self.project, fit="under")
        for window in plan["windows"]:
            self.assertEqual(window["trim_tail_frames"], 0, window["name"])
        self.assertGreater(plan["totals"]["hold_frames"], 0)
        self.assertLess(plan["totals"]["generated_frames"],
                        self.plan["totals"]["generated_frames"])

    def test_seed_policy_matches_the_worker_and_is_unique(self):
        seeds = [w["seed"] for w in self.plan["windows"]]
        self.assertEqual(len(set(seeds)), len(seeds))
        for window in self.plan["windows"]:
            self.assertEqual(window["seed"], 1000 + window["id"] * 977)
            self.assertEqual(window["seed"], plan_io.seed_for(window["id"]))
        retake = plan_windows.plan_from_edl(self.edl, self.project, take=1)
        for window in retake["windows"]:
            self.assertEqual(window["seed"], 1000 + window["id"] * 977 + 7919)

    def test_prompts_keep_canon_and_add_the_camera_lock(self):
        for window in self.plan["windows"]:
            full = window["prompt_full"]
            self.assertIn(window["prompt"], full)
            self.assertIn(self.project["style_block"], full)
            if window["camera"] == "locked":
                self.assertIn("Locked camera", full)
                self.assertIn("No push-in", full)
            else:
                self.assertIn(f"Camera move: {window['camera']}", full)
            if window["pin"] == "same_still":
                self.assertIn("same plate", full)
            self.assertIn("no burned-in lyrics", full.lower())

    def test_refs_are_comfy_names_and_fit_the_seam_node(self):
        for window in self.plan["windows"]:
            self.assertLessEqual(len(window["refs"]), plan_windows.MAX_REFS)
            for ref in window["refs"]:
                self.assertTrue(ref.startswith("dont_freak/"), ref)
                self.assertNotIn("00-band-bible", ref)

    def test_plan_reports_the_stills_that_do_not_exist_yet(self):
        needed = {still["id"] for still in self.plan["needed_stills"]}
        self.assertEqual(len(needed), 9)
        self.assertIn("INJ_SLOTH_STAGE_STAND", needed)
        self.assertNotIn("INJ_STAGE_EMPTY", needed)
        self.assertFalse(self.plan["ready"])
        for still in self.plan["needed_stills"]:
            self.assertTrue(still["windows"])
            self.assertTrue(still["brief"])

    def test_uncertain_lyric_in_is_flagged(self):
        uncertain = self.plan["uncertain_rows"]
        self.assertEqual([row["row"] for row in uncertain], [3])
        self.assertEqual(uncertain[0]["t_sec"], 22.0)
        self.assertIn("force-align", uncertain[0]["notes"])

    def test_checked_in_plan_example_matches_a_fresh_plan(self):
        saved = json.loads((PACK / "plan.example.json").read_text(encoding="utf-8"))
        self.assertEqual(saved, self.plan)


class FitMathTests(unittest.TestCase):
    def test_cover_picks_the_smallest_lattice_that_reaches(self):
        self.assertEqual(plan_windows.choose_length(120, "cover")[0], 124)
        self.assertEqual(plan_windows.choose_length(123, "cover")[0], 124)
        self.assertEqual(plan_windows.choose_length(124, "cover")[0], 243)
        self.assertEqual(plan_windows.choose_length(240, "cover")[0], 243)
        self.assertEqual(plan_windows.choose_length(264, "cover")[0], 362)
        self.assertEqual(plan_windows.choose_length(360, "cover")[0], 362)

    def test_under_picks_the_largest_lattice_that_fits(self):
        self.assertEqual(plan_windows.choose_length(264, "under")[0], 243)
        self.assertEqual(plan_windows.choose_length(122, "under")[0], 124)
        self.assertEqual(plan_windows.choose_length(361, "under")[0], 362)

    def test_nearest_minimises_the_residual(self):
        self.assertEqual(plan_windows.choose_length(264, "nearest")[0], 243)
        self.assertEqual(plan_windows.choose_length(320, "nearest")[0], 362)

    def test_running_out_of_wav_clamps_the_length(self):
        length, clamped = plan_windows.choose_length(276, "cover", max_frames=275)
        self.assertEqual(length, 243)
        self.assertTrue(clamped)
        length, clamped = plan_windows.choose_length(276, "cover", max_frames=5075)
        self.assertEqual(length, 362)
        self.assertFalse(clamped)

    def test_a_window_supplies_nframes_minus_one_new_frames(self):
        for length in plan_windows.LATTICE:
            span = length - 1
            self.assertEqual(plan_windows.choose_length(span, "cover")[0], length)


class PackingTests(unittest.TestCase):
    def _plan(self, hits, duration_s=60.0, **kwargs):
        edl = synthetic_edl(hits, duration_s)
        self.assertEqual(plan_windows.validate_edl(edl), [])
        return plan_windows.plan_from_edl(edl, {}, **kwargs)

    def test_hits_closer_than_the_floor_become_smash_cuts(self):
        # 0 -> 240 -> 300 -> 720: the 300 hit is 60 frames after 240, under 124.
        plan = self._plan([(0.0, "inject"), (10.0, "inject"), (12.5, "inject"), (30.0, "inject")])
        edges = {w["start_frame"] for w in plan["windows"]}
        self.assertNotIn(300, edges)
        smash = plan["smash_cuts"][0]
        self.assertEqual(smash["frame_24"], 300)
        self.assertTrue(smash["auto_demoted"])
        self.assertEqual(smash["inside_window"], 2)

    def test_a_hold_row_is_never_demoted(self):
        plan = self._plan([(0.0, "inject"), (10.0, "inject"), (12.5, "hold"), (30.0, "inject")])
        edges = {w["start_frame"] for w in plan["windows"]}
        self.assertIn(300, edges)
        self.assertEqual(plan["smash_cuts"], [])
        self.assertTrue(any("under the 124f floor" in w for w in plan["warnings"]))

    def test_a_short_final_span_merges_backwards(self):
        # last hit is 48 frames before the end row, so it cannot merge forward
        plan = self._plan([(0.0, "inject"), (10.0, "inject"), (28.0, "inject")], duration_s=30.0)
        self.assertEqual(plan["windows"][-1]["end_frame"], 720)
        self.assertEqual([s["frame_24"] for s in plan["smash_cuts"]], [672])
        self.assertTrue(plan["smash_cuts"][0]["auto_demoted"])

    def test_a_lower_floor_keeps_short_hits_as_windows(self):
        edl = synthetic_edl([(0.0, "inject"), (10.0, "inject"), (12.5, "inject"),
                             (30.0, "inject")], 60.0, min_fill_frames=48)
        plan = plan_windows.plan_from_edl(edl, {})
        self.assertIn(300, {w["start_frame"] for w in plan["windows"]})
        self.assertEqual(plan["smash_cuts"], [])


class WavProbeTests(unittest.TestCase):
    def test_probe_fills_the_exact_numbers(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fixture.wav"
            frames = write_wav(path, seconds=2.5)
            probe = plan_windows.probe_wav(path)
            self.assertEqual(probe["sample_rate"], 48000)
            self.assertEqual(probe["channels"], 2)
            self.assertEqual(probe["codec"], "pcm_s16le")
            self.assertEqual(probe["total_samples"], frames)
            self.assertEqual(probe["duration_s"], 2.5)
            self.assertEqual(probe["frames_24"], 60)
            self.assertEqual(probe["frames_24"], round(probe["duration_s"] * 24))

    def test_probe_agrees_with_the_checked_in_dont_freak_numbers(self):
        audio = plan_windows.load_edl(PACK)["audio"]
        self.assertEqual(round(audio["total_samples"] / audio["sample_rate"], 6),
                         audio["duration_s"])
        self.assertEqual(plan_windows.frame_for(audio["duration_s"]), audio["frames_24"])

    def test_planner_cli_stamps_a_probed_wav(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            write_wav(tmp / "fixture.wav", seconds=30.0)
            edl = synthetic_edl([(0.0, "inject"), (10.0, "inject")], 60.0)
            (tmp / "edl.json").write_text(json.dumps(edl), encoding="utf-8")
            rc = plan_windows.main([str(tmp), "--edl", str(tmp / "edl.json"),
                                    "--wav", str(tmp / "fixture.wav"),
                                    "--out", str(tmp / "plan.json")])
            self.assertEqual(rc, 0)
            plan = json.loads((tmp / "plan.json").read_text(encoding="utf-8"))
            self.assertEqual(plan["audio"]["duration_s"], 30.0)
            self.assertEqual(plan["audio"]["frames_24"], 720)
            self.assertEqual(plan["windows"][-1]["end_frame"], 720)


class GraphTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        edl = plan_windows.load_edl(PACK)
        project = load_project(PACK)
        cls.plan = plan_windows.plan_from_edl(edl, project, audio_input=AUDIO_INPUT)
        cls.window = cls.plan["windows"][10]
        cls.graph = plan_windows.build_window_graph(cls.plan, cls.window)

    def _by_type(self, class_type):
        return [node for node in self.graph.values() if node["class_type"] == class_type]

    def test_graph_drives_the_live_kit_nodes(self):
        for class_type in ("MiniMaxH3SeamToVideo", "SongWindow", "LoadAudio",
                           "LoadImage", "UNETLoader", "LoraLoaderModelOnly"):
            self.assertTrue(self._by_type(class_type), class_type)

    def test_seam_node_gets_both_pinned_frames_and_the_window_length(self):
        seam = self._by_type("MiniMaxH3SeamToVideo")[0]["inputs"]
        self.assertEqual(seam["length"], self.window["nframes"])
        self.assertEqual(seam["width"], 1344)
        self.assertEqual(seam["height"], 768)
        first = self.graph[seam["first_frame"][0]]["inputs"]["image"]
        last = self.graph[seam["last_frame"][0]]["inputs"]["image"]
        self.assertEqual(first, self.window["first_still"])
        self.assertEqual(last, self.window["last_still"])
        self.assertEqual(seam["ref_audio_1"][0],
                         next(k for k, v in self.graph.items() if v["class_type"] == "SongWindow"))
        for i, ref in enumerate(self.window["refs"], start=1):
            self.assertEqual(self.graph[seam[f"ref_image_{i}"][0]]["inputs"]["image"], ref)

    def test_song_window_crops_the_real_wav_not_a_click(self):
        song = self._by_type("SongWindow")[0]["inputs"]
        self.assertEqual(song["offset_s"], self.window["audio_start_s"])
        self.assertEqual(song["duration_s"], self.window["duration_s"])
        self.assertEqual(self.graph[song["audio"][0]]["inputs"]["audio"], AUDIO_INPUT)
        self.assertFalse(self._by_type("BeatPulse"))

    def test_turbo_lora_is_fl2v_eight_step(self):
        lora = self._by_type("LoraLoaderModelOnly")[0]["inputs"]
        self.assertEqual(lora["lora_name"], FL2V_TURBO)
        self.assertEqual(lora["strength_model"], 1.0)
        self.assertEqual(self._by_type("BasicScheduler")[0]["inputs"]["steps"], 8)
        self.assertNotIn(REF2V_TURBO, json.dumps(self.graph))
        self.assertEqual(len(self._by_type("LoraLoaderModelOnly")), 1)

    def test_model_chain_reaches_the_guider(self):
        lora_id = next(k for k, v in self.graph.items()
                       if v["class_type"] == "LoraLoaderModelOnly")
        self.assertEqual(self.graph[lora_id]["inputs"]["model"][0],
                         next(k for k, v in self.graph.items() if v["class_type"] == "UNETLoader"))
        guider = self._by_type("BasicGuider")[0]["inputs"]
        chain = self.graph[guider["model"][0]]["class_type"]
        self.assertIn(chain, ("MiniMaxH3SigmaShift", "H3FirstBlockCache"))
        seam_id = next(k for k, v in self.graph.items()
                       if v["class_type"] == "MiniMaxH3SeamToVideo")
        self.assertEqual(guider["conditioning"], [seam_id, 0])
        self.assertEqual(self._by_type("SamplerCustomAdvanced")[0]["inputs"]["latent_image"],
                         [seam_id, 1])

    def test_every_window_builds_a_graph(self):
        for window in self.plan["windows"]:
            graph = plan_windows.build_window_graph(self.plan, window)
            self.assertEqual(
                graph[next(k for k, v in graph.items()
                           if v["class_type"] == "MiniMaxH3SeamToVideo")]["inputs"]["length"],
                window["nframes"])

    def test_graph_needs_an_audio_input_name(self):
        plan = dict(self.plan, audio_input=None)
        with self.assertRaises(ValueError):
            plan_windows.build_window_graph(plan, self.window)


class NodePackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        edl = plan_windows.load_edl(PACK)
        cls.plan = plan_windows.plan_from_edl(edl, load_project(PACK), audio_input=AUDIO_INPUT)

    def test_pack_imports_without_torch_or_comfy(self):
        """Importing the package must not drag in torch/comfy — this suite has neither."""
        self.assertEqual(set(NODE_CLASS_MAPPINGS), {"H3EDLWindow", "H3EDLStill", "H3EDLSeamCheck"})
        self.assertEqual(set(NODE_DISPLAY_NAME_MAPPINGS), set(NODE_CLASS_MAPPINGS))
        heavy = {"torch", "numpy", "PIL", "comfy", "folder_paths", "node_helpers"}
        for path in (ROOT / "comfy_nodes" / "h3_edl_window").glob("*.py"):
            for node in ast.parse(path.read_text(encoding="utf-8")).body:
                names = []
                if isinstance(node, ast.Import):
                    names = [alias.name.split(".")[0] for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [(node.module or "").split(".")[0]]
                self.assertFalse(heavy & set(names), f"{path.name} imports {names} at module scope")

    def test_nodes_follow_the_comfy_class_contract(self):
        for name, cls in NODE_CLASS_MAPPINGS.items():
            spec = cls.INPUT_TYPES()
            self.assertIn("required", spec, name)
            self.assertTrue(isinstance(cls.RETURN_TYPES, tuple), name)
            self.assertEqual(len(cls.RETURN_TYPES), len(cls.RETURN_NAMES), name)
            self.assertTrue(callable(getattr(cls, cls.FUNCTION)), name)
            self.assertTrue(cls.CATEGORY.startswith("video/"), name)

    def test_node_names_do_not_shadow_the_live_seam_kit(self):
        source = (ROOT / "h3_seam_kit" / "__init__.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        live = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and any(
                    getattr(t, "id", "") == "NODE_CLASS_MAPPINGS" for t in node.targets):
                live = {key.value for key in node.value.keys}
        self.assertIn("MiniMaxH3SeamToVideo", live)
        self.assertIn("SongWindow", live)
        self.assertFalse(live & set(NODE_CLASS_MAPPINGS))

    def test_pack_does_not_import_or_vendor_the_seam_kit(self):
        for path in (ROOT / "comfy_nodes" / "h3_edl_window").glob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertNotIn("h3_seam_kit", alias.name, path.name)
                elif isinstance(node, ast.ImportFrom):
                    self.assertNotIn("h3_seam_kit", node.module or "", path.name)
        kit = (ROOT / "h3_seam_kit" / "__init__.py").read_text(encoding="utf-8")
        for path in (ROOT / "comfy_nodes").rglob("*.py"):
            self.assertNotIn("class MiniMaxH3SeamToVideo", path.read_text(encoding="utf-8"))
        self.assertIn("class MiniMaxH3SeamToVideo", kit)

    def test_window_node_reads_a_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plan.json"
            path.write_text(json.dumps(self.plan), encoding="utf-8")
            out = NODE_CLASS_MAPPINGS["H3EDLWindow"]().run(str(path), 11)
            length, offset, duration, seed, prompt, first, last, count, summary = out
            window = plan_io.window_by_id(self.plan, 11)
            self.assertEqual(length, window["nframes"])
            self.assertEqual(offset, window["audio_start_s"])
            self.assertEqual(duration, window["duration_s"])
            self.assertEqual(seed, window["seed"])
            self.assertEqual(prompt, window["prompt_full"])
            self.assertEqual((first, last), (window["first_still"], window["last_still"]))
            self.assertEqual(count, len(self.plan["windows"]))
            self.assertIn("smash rows 12", summary)
            retake = NODE_CLASS_MAPPINGS["H3EDLWindow"]().run(str(path), 11, take=2)
            self.assertEqual(retake[3], plan_io.seed_for(11, 2))

    def test_seed_policy_agrees_across_repo_and_pack(self):
        for window_id in range(1, 25):
            for take in range(3):
                self.assertEqual(plan_io.seed_for(window_id, take),
                                 plan_windows.seed_for(window_id, take))

    def test_still_resolution_and_seam_identity(self):
        """The pin: window N's last still is the same file as N+1's first."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            input_dir = tmp / "input"
            names = {}
            for window in self.plan["windows"][:3]:
                for key in ("first_still", "last_still"):
                    names[window[key]] = window[f"{key}_id"]
            self.assertGreaterEqual(len(names), 3)
            for i, name in enumerate(sorted(names)):
                path = input_dir / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(png_bytes(rgb=(10 * i, 20 * i, 30 * i)))

            first_window = self.plan["windows"][0]
            second_window = self.plan["windows"][1]
            last_of_first = plan_io.resolve_still(
                plan_io.still_name(first_window, "last"), input_dir)
            first_of_second = plan_io.resolve_still(
                plan_io.still_name(second_window, "first"), input_dir)
            self.assertEqual(last_of_first, first_of_second)
            self.assertEqual(plan_io.sha256_file(last_of_first),
                             plan_io.sha256_file(first_of_second))

            with self.assertRaises(ValueError):
                plan_io.resolve_still("dont_freak/nope.png", input_dir)
            with self.assertRaises(ValueError):
                plan_io.resolve_still("dont_freak/nope.png", None)

    def test_plan_io_rejects_junk(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plan.json"
            path.write_text(json.dumps({"plan_schema": 2, "windows": []}), encoding="utf-8")
            with self.assertRaises(ValueError):
                plan_io.load_plan(path)
            path.write_text(json.dumps({"plan_schema": 1, "windows": []}), encoding="utf-8")
            with self.assertRaises(ValueError):
                plan_io.load_plan(path)
            with self.assertRaises(ValueError):
                plan_io.window_by_id(self.plan, 999)
            with self.assertRaises(ValueError):
                plan_io.still_name({"id": 1}, "first")


class EdlValidationTests(unittest.TestCase):
    def _edl(self):
        return synthetic_edl([(0.0, "inject"), (10.0, "inject")], 60.0)

    def test_a_drifted_frame_number_is_caught(self):
        edl = self._edl()
        edl["rows"][1]["frame_24"] = 241
        self.assertTrue(any("frame_24" in p for p in plan_windows.validate_edl(edl)))

    def test_an_identity_sheet_as_a_cut_frame_is_caught(self):
        edl = self._edl()
        edl["stills"].append({"id": "REF", "role": "identity_ref", "body": "bust"})
        edl["rows"][1]["still"] = "REF"
        problems = plan_windows.validate_edl(edl)
        self.assertTrue(any("never cut frames" in p for p in problems))

    def test_a_collage_as_a_cut_frame_is_caught(self):
        edl = self._edl()
        edl["stills"].append({"id": "BIBLE", "role": "inject", "body": "collage"})
        edl["rows"][1]["still"] = "BIBLE"
        problems = plan_windows.validate_edl(edl)
        self.assertTrue(any("stand on the floor" in p for p in problems))

    def test_a_row_off_the_catalog_timeline_is_caught(self):
        edl = self._edl()
        edl["rows"][1]["shot"] = 2
        project = {"shots": [{"id": 2, "start_s": 11.0}]}
        problems = plan_windows.validate_edl(edl, project)
        self.assertTrue(any("parallel one" in p for p in problems))

    def test_a_missing_end_row_is_caught(self):
        edl = self._edl()
        edl["rows"][-1]["kind"] = "inject"
        problems = plan_windows.validate_edl(edl)
        self.assertTrue(any("kind 'end'" in p for p in problems))

    def test_cats_before_the_cast_rule_are_caught(self):
        edl = self._edl()
        edl["stills"].append({"id": "INJ_CATS", "name": "cat pair", "role": "inject",
                              "body": "standing_full"})
        edl["rows"][1]["still"] = "INJ_CATS"
        problems = plan_windows.validate_edl(edl, {"cast_rules": {"cats_from_s": 95.0}})
        self.assertTrue(any("cats at" in p for p in problems))

    def test_the_real_edl_survives_a_cli_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "plan.json"
            rc = plan_windows.main([str(PACK), "--out", str(out),
                                    "--audio-input", AUDIO_INPUT, "--emit-graph", tmp])
            self.assertEqual(rc, 0)
            plan = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(len(plan["windows"]), 19)
            self.assertEqual(len(list(Path(tmp).glob("w*.json"))), 19)


if __name__ == "__main__":
    unittest.main()
