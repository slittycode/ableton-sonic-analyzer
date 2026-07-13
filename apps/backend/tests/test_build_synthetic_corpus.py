import json
import tempfile
import unittest
from pathlib import Path

from fundamentals_evaluation import (
    _chord_segment_accuracy,
    _keys_match,
    _normalize_chord_label,
)
from scripts.build_synthetic_corpus import (
    _EXPECTED_KEYS_BY_KIND,
    _THRESHOLDS_BY_KIND,
    build_corpus,
    render_ambient_pad,
    render_broken_grid,
    render_chord_progression,
    render_count_pattern,
    render_grid_pattern,
    render_shuffle16_pattern,
    _render_spec,
    _synthetic_specs,
)


class BuildSyntheticCorpusTests(unittest.TestCase):
    def test_check_build_is_deterministic_and_manifest_has_expected_shape(self) -> None:
        with tempfile.TemporaryDirectory(prefix="asa_synth_corpus_") as temp_dir:
            root = Path(temp_dir)
            manifest = root / "fundamentals_eval_manifest.synthetic.json"

            result = build_corpus(root / "tracks", manifest, check=True)

            self.assertEqual(result["tracks"], len(_synthetic_specs()))
            data = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(data["schemaVersion"], "fundamentals-eval.v1")
            self.assertEqual(data["targetProfile"], "electronic_ableton_v1")
            first = data["tracks"][0]
            self.assertIn("id", first)
            self.assertIn("audioPath", first)
            self.assertIn("expected", first)
            self.assertTrue((root / "tracks" / first["audioPath"]).exists())

    def test_no_spec_is_silently_dropped(self) -> None:
        # Codex's original emitted specs[:28], silently dropping the 29th
        # (multi_F_major). Every declared spec must render.
        specs = _synthetic_specs()
        ids = [spec["id"] for spec in specs]
        self.assertIn("multi_F_major", ids)
        self.assertIn("multi_A_minor", ids)
        self.assertEqual(len(ids), len(set(ids)), "duplicate spec ids")

    def test_expected_blocks_carry_only_active_check_keys(self) -> None:
        # Ground-truth-for-later (hitTimes, unchecked fields) must live under
        # "truth", never inside "expected" — otherwise it silently becomes an
        # uncalibrated live check the moment the harness learns the key. Only
        # keys in _EXPECTED_KEYS_BY_KIND for the clip kind may appear.
        with tempfile.TemporaryDirectory(prefix="asa_synth_expected_") as temp_dir:
            root = Path(temp_dir)
            manifest = root / "m.synthetic.json"
            build_corpus(root / "tracks", manifest, check=False)
            data = json.loads(manifest.read_text(encoding="utf-8"))
            for track in data["tracks"]:
                allowed = set(_EXPECTED_KEYS_BY_KIND[track["category"]])
                self.assertLessEqual(
                    set(track["expected"].keys()), allowed,
                    f"{track['id']} expected keys leak beyond active checks",
                )
                self.assertNotIn("hitTimes", track["expected"])

    def test_bass_and_multi_specs_get_their_analyze_flags(self) -> None:
        with tempfile.TemporaryDirectory(prefix="asa_synth_flags_") as temp_dir:
            root = Path(temp_dir)
            manifest = root / "m.synthetic.json"
            build_corpus(root / "tracks", manifest, check=False)
            data = json.loads(manifest.read_text(encoding="utf-8"))
            by_id = {track["id"]: track for track in data["tracks"]}
            self.assertEqual(by_id["mono_bass_transcription"].get("analyzeFlags"), ["--transcribe"])
            self.assertEqual(by_id["multi_A_minor"].get("analyzeFlags"), ["--separate"])

    def test_audio_only_does_not_rewrite_manifest(self) -> None:
        with tempfile.TemporaryDirectory(prefix="asa_synth_audio_only_") as temp_dir:
            root = Path(temp_dir)
            manifest = root / "manifest.json"
            manifest.write_text("sentinel", encoding="utf-8")

            result = build_corpus(root / "tracks", manifest, check=True, write_manifest=False)

            self.assertEqual(result["tracks"], 4)
            self.assertIsNone(result["manifest"])
            self.assertEqual(manifest.read_text(encoding="utf-8"), "sentinel")
            self.assertTrue((root / "tracks" / "four_on_floor_clear_128.wav").exists())

    def test_renders_are_order_independent(self) -> None:
        # One-shots carry their own seeded RNGs, so rendering a single spec in
        # isolation must produce the same bytes as rendering it mid-sequence.
        spec = next(s for s in _synthetic_specs() if s["kind"] == "counts")
        solo = _render_spec(spec).samples.tobytes()
        _render_spec(next(s for s in _synthetic_specs() if s["kind"] == "grid"))
        again = _render_spec(spec).samples.tobytes()
        self.assertEqual(solo, again)

    def test_count_pattern_truth_matches_placement(self) -> None:
        rendered = render_count_pattern(bpm=128, bars=8)
        self.assertEqual(
            rendered.truth["percussion"],
            {"kickCount": 32, "snareCount": 16, "hihatCount": 16},
        )
        self.assertEqual(len(rendered.truth["hitTimes"]["kick"]), 32)

    def test_grid_pattern_truth_grid_and_downbeats(self) -> None:
        rendered = render_grid_pattern(bpm=120, meter="3/4", bars=4)
        self.assertEqual(len(rendered.truth["beatGrid"]), 12)
        self.assertEqual(rendered.truth["downbeats"], [0.0, 1.5, 3.0, 4.5])
        self.assertNotIn("swingPercent", rendered.truth)
        swung = render_grid_pattern(bpm=120, meter="4/4", bars=2, with_hats=True, swing_percent=58)
        self.assertEqual(swung.truth["swingPercent"], 58)
        # First hat "and" lands at 58% of beat 0.
        self.assertAlmostEqual(swung.truth["hitTimes"]["hihat"][0], 0.58 * 0.5, places=4)

    def test_chord_labels_are_flat_spelled_and_fold_enharmonically(self) -> None:
        rendered = render_chord_progression("A", "minor", [1, 6, 7, 5], 120, 4.0)
        labels = [segment["label"] for segment in rendered.truth["chordTimeline"]]
        self.assertEqual(labels, ["Am", "F", "G", "Em"])

        # F# major spells flat (Viterbi vocab) — the original hardcoded table
        # emitted sharps and scored 0.25 against the analyzer.
        sharp = render_chord_progression("F#", "major", [1, 6, 4, 5], 120, 4.0)
        self.assertEqual(
            [segment["label"] for segment in sharp.truth["chordTimeline"]],
            ["Gb", "Ebm", "B", "Db"],
        )
        self.assertEqual(_normalize_chord_label("F#"), _normalize_chord_label("Gb"))
        self.assertEqual(_normalize_chord_label("D#m"), _normalize_chord_label("Ebm"))
        self.assertEqual(_normalize_chord_label("A minor"), _normalize_chord_label("Am"))
        self.assertNotEqual(_normalize_chord_label("Am"), _normalize_chord_label("A"))
        self.assertEqual(_chord_segment_accuracy(rendered.truth["chordTimeline"], rendered.truth["chordTimeline"]), 1.0)

    def test_broken_grid_truth_matches_placement(self) -> None:
        # 2-step at 120 BPM (beat = 0.5 s): kicks at 0 and 1.5 beats, snares
        # at 1 and 3 — the beat grid and downbeats stay on the notated pulse.
        rendered = render_broken_grid(
            bpm=120, bars=2, kick_offsets=(0.0, 1.5), snare_offsets=(1.0, 3.0)
        )
        self.assertEqual(rendered.truth["bpm"], 120)
        self.assertEqual(rendered.truth["timeSignature"], "4/4")
        self.assertEqual(len(rendered.truth["beatGrid"]), 8)
        self.assertEqual(rendered.truth["downbeats"], [0.0, 2.0])
        self.assertEqual(rendered.truth["hitTimes"]["kick"], [0.0, 0.75, 2.0, 2.75])
        self.assertEqual(rendered.truth["hitTimes"]["snare"], [0.5, 1.5, 2.5, 3.5])

    def test_shuffle16_truth_places_swung_16ths(self) -> None:
        rendered = render_shuffle16_pattern(bpm=120, bars=1, swing_percent=62)
        self.assertEqual(rendered.truth["swingPercent"], 62)
        self.assertEqual(rendered.truth["swingGrid"], "16th")
        # First swung 16th: 62% of a half-beat into beat 0 => 0.31 beats = 0.155 s.
        self.assertAlmostEqual(rendered.truth["hitTimes"]["hihat"][0], 0.155, places=4)

    def test_ambient_pad_expected_carries_key_and_honesty_only(self) -> None:
        rendered = render_ambient_pad("A", "minor", 70)
        self.assertEqual(rendered.truth["key"], "A minor")
        self.assertEqual(
            set(rendered.truth["honesty"].keys()),
            {"maxBpmConfidence", "swingDetailAbsent", "meterSources"},
        )
        # chordTimeline stays inert truth: it is not an active ambient check.
        self.assertNotIn("chordTimeline", _EXPECTED_KEYS_BY_KIND["ambient"])
        self.assertIn("chordTimeline", rendered.truth)

    def test_genre_generalization_specs_are_declared(self) -> None:
        ids = {spec["id"] for spec in _synthetic_specs()}
        for expected_id in (
            "grid_4_4_85", "grid_4_4_150", "grid_4_4_190",
            "twostep_132", "halftime_140", "halftime_174",
            "breakbeat_136", "shuffle16_130_62", "ambient_beatless_70",
        ):
            self.assertIn(expected_id, ids)
        # Every declared kind has both check tables filled in.
        for spec in _synthetic_specs():
            self.assertIn(spec["kind"], _EXPECTED_KEYS_BY_KIND)
            self.assertIn(spec["kind"], _THRESHOLDS_BY_KIND)

    def test_keys_match_folds_enharmonics(self) -> None:
        self.assertTrue(_keys_match("C# Minor", "Db minor", allow_relative=False))
        self.assertFalse(_keys_match("C# Major", "Db minor", allow_relative=False))
        self.assertTrue(_keys_match("Eb major", "C minor", allow_relative=True))
        self.assertTrue(_keys_match("D# major", "C minor", allow_relative=True))


if __name__ == "__main__":
    unittest.main()
