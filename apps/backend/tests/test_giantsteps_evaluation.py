import json
import tempfile
import unittest
from pathlib import Path

from giantsteps_evaluation import (
    GiantstepsClip,
    evaluate_corpus,
    load_giantsteps_corpus,
    mirex_key_score,
    tempo_accuracies,
)


class MirexKeyScoreTests(unittest.TestCase):
    def test_score_table(self) -> None:
        self.assertEqual(mirex_key_score("D minor", "D minor"), 1.0)
        self.assertEqual(mirex_key_score("Db minor", "C# Minor"), 1.0)  # enharmonic exact
        self.assertEqual(mirex_key_score("C major", "G major"), 0.5)  # fifth above
        self.assertEqual(mirex_key_score("C major", "F major"), 0.0)  # fifth below ≠ MIREX fifth
        self.assertEqual(mirex_key_score("C major", "A minor"), 0.3)  # relative
        self.assertEqual(mirex_key_score("A minor", "C major"), 0.3)  # relative, other way
        self.assertEqual(mirex_key_score("C major", "C minor"), 0.2)  # parallel
        self.assertEqual(mirex_key_score("C major", "D major"), 0.0)
        self.assertEqual(mirex_key_score("C major", None), 0.0)
        self.assertEqual(mirex_key_score("garbage", "C major"), 0.0)


class TempoAccuracyTests(unittest.TestCase):
    def test_acc1_tolerance_boundary(self) -> None:
        self.assertEqual(tempo_accuracies(128.0, 128.0), (True, True))
        # 4% of 128 = 5.12 — just inside vs just outside the tolerance.
        self.assertEqual(tempo_accuracies(128.0, 133.1), (True, True))
        self.assertEqual(tempo_accuracies(128.0, 133.2)[0], False)

    def test_acc2_octave_and_triple_families(self) -> None:
        self.assertEqual(tempo_accuracies(174.0, 87.0), (False, True))  # half
        self.assertEqual(tempo_accuracies(87.0, 174.0), (False, True))  # double
        self.assertEqual(tempo_accuracies(60.0, 180.0), (False, True))  # triple
        self.assertEqual(tempo_accuracies(180.0, 60.0), (False, True))  # third
        self.assertEqual(tempo_accuracies(128.0, 100.0), (False, False))

    def test_missing_or_invalid_values(self) -> None:
        self.assertEqual(tempo_accuracies(128.0, None), (False, False))
        self.assertEqual(tempo_accuracies(0.0, 128.0), (False, False))


class LoadCorpusTests(unittest.TestCase):
    def test_loads_annotations_and_matches_audio_by_stem(self) -> None:
        with tempfile.TemporaryDirectory(prefix="asa_giantsteps_") as temp_dir:
            root = Path(temp_dir)
            (root / "key" / "annotations").mkdir(parents=True)
            (root / "key" / "audio").mkdir(parents=True)
            (root / "key" / "annotations" / "111.LOFI.key").write_text("D minor")
            (root / "key" / "annotations" / "222.LOFI.key").write_text("Ab major")
            (root / "key" / "audio" / "111.LOFI.mp3").write_bytes(b"x")

            clips = load_giantsteps_corpus(root, "key")

            self.assertEqual([c.clip_id for c in clips], ["111.LOFI", "222.LOFI"])
            self.assertTrue(clips[0].audio_path.exists())
            self.assertFalse(clips[1].audio_path.exists())
            self.assertEqual(clips[0].expected_key, "D minor")

    def test_parses_bpm_annotations(self) -> None:
        with tempfile.TemporaryDirectory(prefix="asa_giantsteps_") as temp_dir:
            root = Path(temp_dir)
            (root / "tempo" / "annotations").mkdir(parents=True)
            (root / "tempo" / "annotations" / "333.LOFI.bpm").write_text("137.5\n")
            (root / "tempo" / "annotations" / "444.LOFI.bpm").write_text("not-a-number")

            clips = load_giantsteps_corpus(root, "tempo")

            self.assertEqual(clips[0].expected_bpm, 137.5)
            self.assertIsNone(clips[1].expected_bpm)

    def test_missing_directory_returns_empty(self) -> None:
        self.assertEqual(load_giantsteps_corpus(Path("/nonexistent"), "key"), [])


class EvaluateCorpusTests(unittest.TestCase):
    def _clip(self, tmp: Path, clip_id: str, *, key: str | None = None, bpm: float | None = None, audio: bool = True) -> GiantstepsClip:
        audio_path = tmp / f"{clip_id}.mp3"
        if audio:
            audio_path.write_bytes(b"x")
        return GiantstepsClip(clip_id=clip_id, audio_path=audio_path, expected_key=key, expected_bpm=bpm)

    def test_key_subset_aggregates_mirex_rates(self) -> None:
        with tempfile.TemporaryDirectory(prefix="asa_gs_eval_") as temp_dir:
            tmp = Path(temp_dir)
            clips = [
                self._clip(tmp, "exact", key="D minor"),
                self._clip(tmp, "relative", key="C major"),
                self._clip(tmp, "wrong", key="E major"),
            ]
            answers = {"exact": "D minor", "relative": "A minor", "wrong": "Bb minor"}

            def runner(path: Path, flags):
                self.assertEqual(flags, ["--fast"])
                return {"key": answers[path.stem]}

            report = evaluate_corpus(clips, subset="key", runner=runner, report_path=tmp / "r.json")

            summary = report["summary"]
            self.assertEqual(summary["status"], "evaluated")
            self.assertEqual(summary["clipsEvaluated"], 3)
            self.assertAlmostEqual(summary["keyExactRate"], 1 / 3, places=4)
            self.assertAlmostEqual(summary["keyExactOrRelativeRate"], 2 / 3, places=4)
            self.assertAlmostEqual(summary["mirexWeighted"], (1.0 + 0.3 + 0.0) / 3, places=4)
            self.assertTrue((tmp / "r.json").exists())

    def test_tempo_subset_counts_acc1_acc2(self) -> None:
        with tempfile.TemporaryDirectory(prefix="asa_gs_eval_") as temp_dir:
            tmp = Path(temp_dir)
            clips = [
                self._clip(tmp, "hit", bpm=128.0),
                self._clip(tmp, "octave", bpm=174.0),
            ]
            answers = {"hit": 128.2, "octave": 87.0}

            def runner(path: Path, flags):
                return {"bpm": answers[path.stem]}

            report = evaluate_corpus(clips, subset="tempo", runner=runner)

            summary = report["summary"]
            self.assertEqual(summary["tempoAcc1"], 0.5)
            self.assertEqual(summary["tempoAcc2"], 1.0)

    def test_empty_or_missing_audio_is_underpowered_not_green(self) -> None:
        with tempfile.TemporaryDirectory(prefix="asa_gs_eval_") as temp_dir:
            tmp = Path(temp_dir)
            clips = [self._clip(tmp, "ghost", key="C major", audio=False)]

            def runner(path: Path, flags):  # pragma: no cover - must not be called
                raise AssertionError("runner must not run for missing audio")

            report = evaluate_corpus(clips, subset="key", runner=runner)

            self.assertEqual(report["summary"]["status"], "underpowered")
            self.assertEqual(report["summary"]["clipsMissingAudio"], 1)

    def test_max_clips_limits_work(self) -> None:
        with tempfile.TemporaryDirectory(prefix="asa_gs_eval_") as temp_dir:
            tmp = Path(temp_dir)
            clips = [self._clip(tmp, f"c{i}", key="C major") for i in range(5)]
            calls: list[str] = []

            def runner(path: Path, flags):
                calls.append(path.stem)
                return {"key": "C major"}

            evaluate_corpus(clips, subset="key", runner=runner, max_clips=2)
            self.assertEqual(len(calls), 2)

    def test_parallel_jobs_match_sequential(self) -> None:
        with tempfile.TemporaryDirectory(prefix="asa_gs_eval_") as temp_dir:
            tmp = Path(temp_dir)
            keys = ["D minor", "C major", "E major", "A minor", "F# minor", "G major"]
            clips = [self._clip(tmp, f"c{i}", key=keys[i % len(keys)]) for i in range(12)]
            answers = {clip.clip_id: keys[i % len(keys)] for i, clip in enumerate(clips)}

            def runner(path: Path, flags):  # pure + thread-safe
                return {"key": answers[path.stem]}

            seq = evaluate_corpus(clips, subset="key", runner=runner, jobs=1)
            par = evaluate_corpus(clips, subset="key", runner=runner, jobs=4)
            self.assertEqual(par["summary"], seq["summary"])
            self.assertEqual(par["clips"], seq["clips"])  # order preserved


if __name__ == "__main__":
    unittest.main()
