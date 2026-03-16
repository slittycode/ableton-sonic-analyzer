import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class GenreCheckScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.backend_root = Path(__file__).resolve().parents[1]
        cls.script_path = cls.backend_root / "scripts" / "genre_check.py"
        if not cls.script_path.exists():
            raise AssertionError(f"genre_check.py not found at {cls.script_path}")

    def _run_script(self, payload: dict) -> list[str]:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(payload, handle)
            handle.flush()
            json_path = Path(handle.name)

        self.addCleanup(lambda: json_path.unlink(missing_ok=True))

        completed = subprocess.run(
            [sys.executable, str(self.script_path), str(json_path)],
            cwd=self.backend_root,
            capture_output=True,
            text=True,
            check=False,
        )

        if completed.returncode != 0:
            raise AssertionError(
                "genre_check.py failed.\n"
                f"stdout:\n{completed.stdout}\n"
                f"stderr:\n{completed.stderr}"
            )

        return completed.stdout.strip().splitlines()

    def test_reports_expected_signals_for_loose_psychedelic_profile(self) -> None:
        output = self._run_script(
            {
                "bpm": 108.1,
                "grooveDetail": {
                    "kickSwing": 0.8586,
                    "kickAccent": [
                        0.0573,
                        0.2122,
                        0.1315,
                        0.0045,
                        0.6767,
                        0.5701,
                        0.5039,
                        0.0579,
                        0.2069,
                        0.1387,
                        0.0777,
                        0.3843,
                        0.0948,
                        0.5752,
                        0.0929,
                        0.0,
                    ],
                },
                "synthesisCharacter": {
                    "inharmonicity": 0.1407,
                    "oddToEvenRatio": 1.3543,
                },
                "sidechainDetail": {
                    "pumpingStrength": 0.2809,
                    "pumpingConfidence": 0.2635,
                },
            }
        )

        self.assertEqual(
            output,
            [
                "Rhythm cluster: LOOSE_PSYCHEDELIC",
                "Synthesis tier: FM_CHARACTER",
                "Sidechain: NOT_DETECTED",
                "BPM: 108.1",
                "kickSwing: 0.8586",
                "kickAccentVariance: 0.0484",
                "inharmonicity: 0.1407",
            ],
        )
        self.assertNotIn("ACID", "\n".join(output))
        self.assertNotIn("HOUSE", "\n".join(output))
        self.assertNotIn("ELECTRO", "\n".join(output))

    def test_prefers_tight_mechanical_before_no_pulse_when_rules_overlap(self) -> None:
        output = self._run_script(
            {
                "bpm": 130.0,
                "grooveDetail": {
                    "kickSwing": 0.0,
                    "kickAccent": [
                        0.0,
                        0.0,
                        0.0,
                        0.0014,
                        0.0028,
                        0.0,
                        0.0012,
                        0.667,
                        0.0014,
                        0.0603,
                        0.0017,
                        0.0185,
                        0.0,
                        0.0001,
                        0.0,
                        0.0,
                    ],
                },
                "synthesisCharacter": {
                    "inharmonicity": 0.2165,
                    "oddToEvenRatio": 1.6064,
                },
                "sidechainDetail": {
                    "pumpingStrength": 0.309,
                    "pumpingConfidence": 0.3209,
                },
            }
        )

        self.assertEqual(output[0], "Rhythm cluster: TIGHT_MECHANICAL")
        self.assertEqual(output[1], "Synthesis tier: FM_CHARACTER")
        self.assertEqual(output[2], "Sidechain: NOT_DETECTED")
        self.assertEqual(output[3], "BPM: 130.0")
        self.assertEqual(output[4], "kickSwing: 0.0000")
        self.assertEqual(output[5], "kickAccentVariance: 0.0258")
        self.assertEqual(output[6], "inharmonicity: 0.2165")

    def test_falls_back_to_ambiguous_and_na_when_measurements_are_missing(self) -> None:
        output = self._run_script(
            {
                "bpm": None,
                "grooveDetail": {
                    "kickSwing": None,
                    "kickAccent": None,
                },
                "synthesisCharacter": {
                    "inharmonicity": None,
                    "oddToEvenRatio": None,
                },
                "sidechainDetail": {
                    "pumpingStrength": None,
                    "pumpingConfidence": None,
                },
            }
        )

        self.assertEqual(
            output,
            [
                "Rhythm cluster: AMBIGUOUS",
                "Synthesis tier: MIXED",
                "Sidechain: NOT_DETECTED",
                "BPM: N/A",
                "kickSwing: N/A",
                "kickAccentVariance: N/A",
                "inharmonicity: N/A",
            ],
        )


if __name__ == "__main__":
    unittest.main()
