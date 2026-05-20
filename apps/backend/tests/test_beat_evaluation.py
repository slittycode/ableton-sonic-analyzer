import importlib.util
import json
import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _load_module():
    spec = importlib.util.spec_from_file_location("beat_evaluation_under_test", BACKEND_DIR / "beat_evaluation.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


be = _load_module()


def _write_click_wav(path: Path, *, sr: int = 44100, bpm: int = 120, bars: int = 8, meter: int = 4) -> None:
    beat = 60.0 / bpm
    total = int(sr * beat * meter * bars)
    x = np.zeros(total, dtype=np.float64)
    for index in range(bars * meter):
        start = int(index * beat * sr)
        dur = int(0.12 * sr)
        env = np.exp(-np.arange(dur) / (0.04 * sr))
        freq, amp = (55.0, 1.0) if index % meter == 0 else (4000.0, 0.25)
        seg = amp * env * np.sin(2 * np.pi * freq * np.arange(dur) / sr)
        end = min(start + dur, total)
        x[start:end] += seg[: end - start]
    x /= np.max(np.abs(x)) + 1e-9
    pcm = (x * 0.9 * 32767).astype("<i2")
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(sr)
        writer.writeframes(pcm.tobytes())


def _write_annotation(path: Path, *, bpm: int = 120, bars: int = 8, meter: int = 4) -> None:
    beat = 60.0 / bpm
    lines = [f"{i * beat:.3f} {(i % meter) + 1}" for i in range(bars * meter)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class ParseGtzanRhythmTests(unittest.TestCase):
    def test_parses_beats_downbeats_meter_tempo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ann = Path(tmp) / "x.beats"
            ann.write_text(
                "\n".join(
                    [
                        "0.000 1", "0.500 2", "1.000 3", "1.500 4",
                        "2.000 1", "2.500 2", "3.000 3", "3.500 4", "4.000 1",
                    ]
                ),
                encoding="utf-8",
            )
            ref = be._parse_gtzan_rhythm(ann)
        self.assertEqual(len(ref["beats"]), 9)
        self.assertEqual(ref["downbeats"], [0.0, 2.0, 4.0])
        self.assertEqual(ref["meter"], 4)
        self.assertAlmostEqual(ref["tempo"], 120.0, places=3)

    def test_three_four_meter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ann = Path(tmp) / "y.beats"
            ann.write_text(
                "\n".join(f"{i * 0.5:.3f} {(i % 3) + 1}" for i in range(12)),
                encoding="utf-8",
            )
            ref = be._parse_gtzan_rhythm(ann)
        self.assertEqual(ref["meter"], 3)
        self.assertEqual(len(ref["downbeats"]), 4)


class MetricTests(unittest.TestCase):
    def test_handroll_f1_perfect_miss_partial(self) -> None:
        self.assertEqual(be._handroll_f1([0, 1, 2, 3], [0, 1, 2, 3]), 1.0)
        self.assertEqual(be._handroll_f1([0, 1, 2], [5, 6, 7]), 0.0)
        # 2 of 4 detected, both correct → P=1.0, R=0.5, F1=0.667
        self.assertAlmostEqual(be._handroll_f1([0, 1, 2, 3], [0, 1]), 2 / 3, places=3)

    def test_downbeat_tolerant_recovers_phase(self) -> None:
        # beats > TRIM_SECONDS so trimming keeps them; ref downbeats sit on phase 1.
        est_beats = [6.0, 6.5, 7.0, 7.5, 8.0, 8.5, 9.0, 9.5, 10.0, 10.5, 11.0, 11.5]
        ref_db = [6.5, 8.5, 10.5]
        mir = be._load_mir_eval()
        strict = be._fmeasure(ref_db, est_beats[0::4], mir)  # phase 0 → wrong
        tolerant = be._downbeat_tolerant(ref_db, est_beats, 4, mir)
        self.assertLess(strict, 0.5)
        self.assertGreater(tolerant, 0.99)


class GateTests(unittest.TestCase):
    def _summary(self, downbeat: float, beat: float = 0.9) -> dict:
        return {"downbeatF1Strict": downbeat, "beatF1": beat, "clipsScored": 250}

    def test_underpowered(self) -> None:
        gate = be.summarize_beat_gate({"kick_accent": self._summary(0.5)}, asa_relevant_clip_count=10)
        self.assertEqual(gate["productRecommendation"], "underpowered")

    def test_pending_beat_this(self) -> None:
        gate = be.summarize_beat_gate(
            {"stride": self._summary(0.4), "kick_accent": self._summary(0.5)},
            asa_relevant_clip_count=250,
        )
        self.assertEqual(gate["productRecommendation"], "pending_beat_this")

    def test_adopt_when_margin_met(self) -> None:
        gate = be.summarize_beat_gate(
            {
                "stride": self._summary(0.3),
                "kick_accent": self._summary(0.50, beat=0.90),
                "beat_this": self._summary(0.65, beat=0.90),
            },
            asa_relevant_clip_count=250,
        )
        self.assertEqual(gate["productRecommendation"], "adopt_pending_asa_slice")
        self.assertTrue(gate["successCriteria"]["downbeatGainAtLeastMargin"])

    def test_keep_heuristic_when_gain_small(self) -> None:
        gate = be.summarize_beat_gate(
            {
                "kick_accent": self._summary(0.60, beat=0.90),
                "beat_this": self._summary(0.63, beat=0.90),
            },
            asa_relevant_clip_count=250,
        )
        self.assertEqual(gate["productRecommendation"], "keep_heuristic")

    def test_keep_heuristic_when_beat_regresses(self) -> None:
        # Downbeat gain is large but beat_this tanks beat tracking → not adopt.
        gate = be.summarize_beat_gate(
            {
                "kick_accent": self._summary(0.50, beat=0.90),
                "beat_this": self._summary(0.70, beat=0.50),
            },
            asa_relevant_clip_count=250,
        )
        self.assertEqual(gate["productRecommendation"], "keep_heuristic")
        self.assertFalse(gate["successCriteria"]["noBeatRegression"])


class EndToEndTests(unittest.TestCase):
    def test_stride_and_kick_accent_on_click_track(self) -> None:
        try:
            import essentia.standard  # noqa: F401
        except Exception:
            self.skipTest("essentia not available in this environment")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            _write_click_wav(tmp_path / "clip.wav")
            _write_annotation(tmp_path / "clip.beats")
            manifest = {
                "datasetName": "self-test",
                "clips": [
                    {
                        "id": "clip",
                        "genre": "techno",
                        "audioPath": "clip.wav",
                        "annotationPath": "clip.beats",
                        "asaRelevant": True,
                    }
                ],
            }
            manifest_path = tmp_path / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            report = be.run_beat_evaluation(
                manifest_path=manifest_path,
                report_path=tmp_path / "report.json",
                output_dir=tmp_path,
                methods=("stride", "kick_accent"),
            )

        self.assertIn(report["metricsBackend"], {"mir_eval", "handrolled_fallback"})
        self.assertEqual(report["evaluatedClipCount"], 1)
        clip = report["clips"][0]
        self.assertEqual(clip["status"], "evaluated")
        for method in ("stride", "kick_accent"):
            self.assertIn(method, clip["methods"])
            metrics = clip["methods"][method]["metrics"]
            self.assertIsNotNone(metrics)
            self.assertGreaterEqual(metrics["beatF1"], 0.0)
            self.assertLessEqual(metrics["beatF1"], 1.0)
            self.assertGreaterEqual(metrics["downbeatF1Strict"], 0.0)
            self.assertLessEqual(metrics["downbeatF1Strict"], 1.0)
        self.assertIn("productRecommendation", report["gate"])
        self.assertTrue(report["researchOnly"])


if __name__ == "__main__":
    unittest.main()
