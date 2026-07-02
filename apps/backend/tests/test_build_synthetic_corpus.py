import json
import tempfile
import unittest
from pathlib import Path

from fundamentals_evaluation import _chord_segment_accuracy
from scripts.build_synthetic_corpus import build_corpus, render_chord_progression, render_drum_pattern


class BuildSyntheticCorpusTests(unittest.TestCase):
    def test_check_build_is_deterministic_and_manifest_has_expected_shape(self) -> None:
        with tempfile.TemporaryDirectory(prefix="asa_synth_corpus_") as temp_dir:
            root = Path(temp_dir)
            manifest = root / "fundamentals_eval_manifest.synthetic.json"

            result = build_corpus(root / "tracks", manifest, check=True)

            self.assertGreaterEqual(result["tracks"], 28)
            data = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(data["schemaVersion"], "fundamentals-eval.v1")
            self.assertEqual(data["targetProfile"], "electronic_ableton_v1")
            self.assertGreaterEqual(len(data["tracks"]), 28)
            first = data["tracks"][0]
            self.assertIn("id", first)
            self.assertIn("audioPath", first)
            self.assertIn("expected", first)
            self.assertTrue((root / "tracks" / first["audioPath"]).exists())

    def test_drum_truth_counts_and_grid_match_requested_pattern(self) -> None:
        rendered = render_drum_pattern(
            120,
            "4/4",
            2,
            kick_positions=[0, 4],
            snare_positions=[2, 6],
            hat_positions=[index * 0.5 for index in range(16)],
            swing_percent=58,
        )

        self.assertEqual(rendered.truth["percussion"], {"kickCount": 2, "snareCount": 2, "hihatCount": 16})
        self.assertEqual(len(rendered.truth["beatGrid"]), 8)
        self.assertEqual(rendered.truth["downbeats"], [0.0, 2.0])
        self.assertEqual(rendered.truth["swingPercent"], 58)

    def test_chord_labels_survive_segment_accuracy_compare(self) -> None:
        rendered = render_chord_progression("A", "minor", [1, 6, 7, 5], 120, 4.0)
        expected = rendered.truth["chordTimeline"]

        self.assertEqual([segment["label"] for segment in expected], ["Am", "F", "G", "Em"])
        self.assertEqual(_chord_segment_accuracy(expected, expected), 1.0)


if __name__ == "__main__":
    unittest.main()
