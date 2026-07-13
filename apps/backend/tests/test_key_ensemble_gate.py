"""Unit tests for the pre-registered key-ensemble decision gate (PR-B3).

Covers the two pure decision components — majority-vote resolution and the
frozen adopt/keep rule — plus an end-to-end run through a stubbed analyzer so
the corpus-iteration and scoring wiring is exercised without real audio.
"""

import tempfile
import unittest
from pathlib import Path

from giantsteps_evaluation import GiantstepsClip
from key_ensemble_gate import (
    EXACT_REGRESSION_TOLERANCE,
    MIN_EVALUABLE,
    MIREX_GAIN_MIN,
    apply_decision_rule,
    resolve_vote,
    run_gate,
)


def _profiles(*keys: str) -> list[dict]:
    names = ("edma", "temperley", "krumhansl")
    return [{"profile": names[i], "key": k, "strength": 0.8} for i, k in enumerate(keys)]


class ResolveVoteTests(unittest.TestCase):
    def test_majority_two_of_three_wins(self) -> None:
        # temperley+krumhansl agree on G minor, overriding EDMA's D minor.
        self.assertEqual(resolve_vote(_profiles("D minor", "G minor", "G minor"), "D minor"), "G minor")

    def test_unanimous(self) -> None:
        self.assertEqual(resolve_vote(_profiles("A minor", "A minor", "A minor"), "A minor"), "A minor")

    def test_all_distinct_keeps_edma(self) -> None:
        self.assertEqual(resolve_vote(_profiles("D minor", "G minor", "A minor"), "D minor"), "D minor")

    def test_edma_in_majority_keeps_edma(self) -> None:
        self.assertEqual(resolve_vote(_profiles("D minor", "D minor", "A minor"), "D minor"), "D minor")

    def test_empty_profiles_keeps_edma(self) -> None:
        self.assertEqual(resolve_vote([], "F# minor"), "F# minor")


class DecisionRuleTests(unittest.TestCase):
    def test_adopt_when_gain_met_and_no_regression(self) -> None:
        edma = {"mirexWeighted": 0.70, "keyExactRate": 0.60}
        vote = {"mirexWeighted": 0.73, "keyExactRate": 0.61}  # +0.03 mirex, +0.01 exact
        d = apply_decision_rule(edma, vote, evaluable=500)
        self.assertEqual(d["decision"], "adopt_vote")
        self.assertTrue(d["adopt"])

    def test_keep_when_gain_below_bar(self) -> None:
        edma = {"mirexWeighted": 0.70, "keyExactRate": 0.60}
        vote = {"mirexWeighted": 0.715, "keyExactRate": 0.62}  # +0.015 < 0.02
        d = apply_decision_rule(edma, vote, evaluable=500)
        self.assertEqual(d["decision"], "keep_edma")

    def test_keep_when_exact_regresses_beyond_tolerance(self) -> None:
        edma = {"mirexWeighted": 0.70, "keyExactRate": 0.60}
        vote = {"mirexWeighted": 0.75, "keyExactRate": 0.585}  # -0.015 < -0.01 tolerance
        d = apply_decision_rule(edma, vote, evaluable=500)
        self.assertEqual(d["decision"], "keep_edma")

    def test_underpowered_never_adopts(self) -> None:
        edma = {"mirexWeighted": 0.70, "keyExactRate": 0.60}
        vote = {"mirexWeighted": 0.80, "keyExactRate": 0.70}  # huge gain
        d = apply_decision_rule(edma, vote, evaluable=MIN_EVALUABLE - 1)
        self.assertEqual(d["decision"], "underpowered")
        self.assertFalse(d["adopt"])

    def test_constants_match_pre_registration(self) -> None:
        self.assertEqual(MIREX_GAIN_MIN, 0.02)
        self.assertEqual(EXACT_REGRESSION_TOLERANCE, 0.01)
        self.assertEqual(MIN_EVALUABLE, 400)


class RunGateTests(unittest.TestCase):
    def test_end_to_end_with_stub_runner(self) -> None:
        with tempfile.TemporaryDirectory(prefix="asa_gate_") as tmp:
            root = Path(tmp)
            audio = root / "a.mp3"
            audio.write_bytes(b"x")
            clips = [
                GiantstepsClip("flip", audio, "G minor", None),   # vote corrects EDMA
                GiantstepsClip("agree", audio, "A minor", None),  # both right
            ]

            def stub(path: Path, flags):  # noqa: ARG001
                # Distinguish clips is unnecessary; the stub returns a fixed payload
                # where EDMA reads D minor but temperley+krumhansl vote G minor.
                return {
                    "key": "D minor",
                    "keyEnsemble": {"profiles": _profiles("D minor", "G minor", "G minor")},
                }

            report = run_gate(clips, runner=stub)
            summary = report["summary"]
            self.assertEqual(summary["clipsEvaluable"], 2)
            self.assertEqual(summary["voteFlips"], 2)  # vote -> G minor on both
            # EDMA D minor vs truths (G minor, A minor): 0.0 + 0.3(relative? no) ...
            # G minor truth, D minor est: fifth above same mode -> 0.5; A minor truth, D minor: 0.0
            self.assertAlmostEqual(summary["edma"]["mirexWeighted"], round((0.5 + 0.0) / 2, 4))
            # Vote G minor vs truths: G minor exact 1.0; A minor truth, G minor est: 0.0
            self.assertAlmostEqual(summary["vote"]["mirexWeighted"], round((1.0 + 0.0) / 2, 4))
            self.assertEqual(summary["vote"]["keyExactRate"], 0.5)

    def test_parallel_jobs_match_sequential(self) -> None:
        with tempfile.TemporaryDirectory(prefix="asa_gate_par_") as tmp:
            root = Path(tmp)
            audio = root / "a.mp3"
            audio.write_bytes(b"x")
            truths = ["G minor", "A minor", "D minor", "F# minor", "C major", "E minor"]
            clips = [GiantstepsClip(f"c{i}", audio, truths[i % len(truths)], None) for i in range(12)]

            def stub(path: Path, flags):  # noqa: ARG001 — pure + thread-safe
                return {"key": "D minor", "keyEnsemble": {"profiles": _profiles("D minor", "G minor", "G minor")}}

            seq = run_gate(clips, runner=stub, jobs=1)
            par = run_gate(clips, runner=stub, jobs=4)
            self.assertEqual(par["summary"], seq["summary"])
            self.assertEqual(par["clips"], seq["clips"])


if __name__ == "__main__":
    unittest.main()
