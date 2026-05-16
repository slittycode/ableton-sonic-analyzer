"""Locks in the Phase 2 gerund-fix post-process (audit final round).

Gemini consistently emits 3rd-person singular forms after "by" in role/reason
text:
    "Shapes drum impact by recreates the harmonic distortion"
    "Controls bass energy by shapes the synthesized sub bass"
    "Supports melodic clarity by matches the highest confidence"

The audit's stated fix path was a server-side post-process after the prompt
instruction didn't take. This test suite documents the conversion rules and
guards against regressions.
"""
import unittest

from server_phase2 import (
    _apply_phase2_grammar_fixes,
    _fix_by_gerund_in_text,
    _to_gerund,
)


class ToGerundTests(unittest.TestCase):
    """Stem-extraction + gerund-formation rules. No regex, just orthography."""

    def test_simple_consonant_stem(self):
        # absorbs → absorb → absorbing
        self.assertEqual(_to_gerund("absorbs"), "absorbing")
        self.assertEqual(_to_gerund("restricts"), "restricting")
        self.assertEqual(_to_gerund("adds"), "adding")

    def test_consonant_doubling_exceptions(self):
        # English consonant-doubling at the gerund is stress-conditional and
        # not implemented algorithmically — covered by _GERUND_IRREGULARS in
        # server_phase2.py. Extend that map (not the regex) when a new verb
        # surfaces in Phase 2 output.
        self.assertEqual(_to_gerund("controls"), "controlling")
        self.assertEqual(_to_gerund("submits"), "submitting")
        self.assertEqual(_to_gerund("runs"), "running")
        self.assertEqual(_to_gerund("commits"), "committing")
        self.assertEqual(_to_gerund("begins"), "beginning")

    def test_silent_e_dropped(self):
        # shapes → shape → shap + ing → shaping
        self.assertEqual(_to_gerund("shapes"), "shaping")
        self.assertEqual(_to_gerund("recreates"), "recreating")
        self.assertEqual(_to_gerund("generates"), "generating")
        self.assertEqual(_to_gerund("provides"), "providing")
        self.assertEqual(_to_gerund("ensures"), "ensuring")
        self.assertEqual(_to_gerund("balances"), "balancing")

    def test_sibilant_endings(self):
        # matches (V-tch + es) → match + ing → matching
        self.assertEqual(_to_gerund("matches"), "matching")
        # passes (V-ss + es) → pass + ing → passing
        self.assertEqual(_to_gerund("passes"), "passing")
        # boxes (V-x + es) → box + ing → boxing
        self.assertEqual(_to_gerund("boxes"), "boxing")
        # crushes (V-sh + es) → crush + ing → crushing
        self.assertEqual(_to_gerund("crushes"), "crushing")
        # catches (V-tch + es) → catch + ing → catching
        self.assertEqual(_to_gerund("catches"), "catching")


class FixByGerundInTextTests(unittest.TestCase):
    """End-to-end string rewrites — the kind that come out of Gemini."""

    def test_actual_screenshot_corpus(self):
        # From `/tmp/asa-shots-audit-final/14-mix-chain-viewport.png`:
        cases = [
            (
                "Shapes drum impact by recreates the aggressive harmonic character.",
                "Shapes drum impact by recreating the aggressive harmonic character.",
            ),
            (
                "Shapes drum impact by absorbs harsh transients.",
                "Shapes drum impact by absorbing harsh transients.",
            ),
            (
                "Controls bass energy by shapes the synthesized sub bass envelope.",
                "Controls bass energy by shaping the synthesized sub bass envelope.",
            ),
            (
                "Controls bass energy by ensures the sub frequencies remain present.",
                "Controls bass energy by ensuring the sub frequencies remain present.",
            ),
            (
                "Supports melodic clarity by matches the highest confidence range.",
                "Supports melodic clarity by matching the highest confidence range.",
            ),
            (
                "Supports melodic clarity by generates the thick, detuned pad.",
                "Supports melodic clarity by generating the thick, detuned pad.",
            ),
            (
                "Balances the center band by provides the ambient tail.",
                "Balances the center band by providing the ambient tail.",
            ),
            (
                "Finalizes the master bus by restricts the output ceiling.",
                "Finalizes the master bus by restricting the output ceiling.",
            ),
        ]
        for original, expected in cases:
            with self.subTest(original=original):
                self.assertEqual(_fix_by_gerund_in_text(original), expected)

    def test_does_not_touch_correct_gerund(self):
        # Already-correct text passes through unchanged.
        self.assertEqual(
            _fix_by_gerund_in_text("Shapes drum impact by recreating the THD."),
            "Shapes drum impact by recreating the THD.",
        )

    def test_preserves_plural_nouns(self):
        # Plural nouns after "by" must not be misinterpreted as verbs.
        denylist_cases = [
            "Triggered by samples played in sequence.",
            "Filtered by bands at 200 Hz and 2 kHz.",
            "Routed by buses sharing the same return.",
            "Quantized by beats per measure.",
            "Driven by levels above -10 dB.",
        ]
        for case in denylist_cases:
            with self.subTest(case=case):
                self.assertEqual(_fix_by_gerund_in_text(case), case)

    def test_short_words_not_rewritten(self):
        # Words shorter than 4 chars after "by" stay intact (avoids
        # converting "by ads", "by ANNs", etc.).
        self.assertEqual(
            _fix_by_gerund_in_text("Compressed by ads on the radio."),
            "Compressed by ads on the radio.",
        )

    def test_empty_and_non_string_input(self):
        self.assertEqual(_fix_by_gerund_in_text(""), "")
        self.assertEqual(_fix_by_gerund_in_text(None), None)
        self.assertEqual(_fix_by_gerund_in_text(42), 42)

    def test_capitalization_at_sentence_start_unaffected(self):
        # Regex only matches lowercase "by" — initial "By" remains as-is.
        # This is acceptable: producer-facing role/reason fields don't start
        # with "By" in practice (sentences begin with "Shapes...", "Controls...").
        self.assertEqual(
            _fix_by_gerund_in_text("By recreates the THD"),
            "By recreates the THD",
        )

    def test_multiple_rewrites_in_one_string(self):
        original = (
            "Shapes drum impact by recreates the THD and balances the mix "
            "by limits the dynamics."
        )
        expected = (
            "Shapes drum impact by recreating the THD and balances the mix "
            "by limiting the dynamics."
        )
        self.assertEqual(_fix_by_gerund_in_text(original), expected)


class ApplyPhase2GrammarFixesTests(unittest.TestCase):
    """The wiring that walks the Phase 2 record and applies the fix in-place."""

    def test_rewrites_mix_chain_reasons(self):
        normalized = {
            "mixAndMasterChain": [
                {
                    "order": 1,
                    "device": "Drum Buss",
                    "reason": "Shapes drum impact by recreates the THD.",
                },
                {
                    "order": 2,
                    "device": "Limiter",
                    "reason": "Finalizes loudness by restricts peaks.",
                },
            ]
        }
        _apply_phase2_grammar_fixes(normalized)
        self.assertEqual(
            normalized["mixAndMasterChain"][0]["reason"],
            "Shapes drum impact by recreating the THD.",
        )
        self.assertEqual(
            normalized["mixAndMasterChain"][1]["reason"],
            "Finalizes loudness by restricting peaks.",
        )

    def test_rewrites_ableton_recommendations_reason_and_advanced_tip(self):
        normalized = {
            "abletonRecommendations": [
                {
                    "device": "Operator",
                    "reason": "Controls bass energy by shapes the sub.",
                    "advancedTip": "Modulate the coarse by adjusts the macro.",
                }
            ]
        }
        _apply_phase2_grammar_fixes(normalized)
        rec = normalized["abletonRecommendations"][0]
        self.assertEqual(rec["reason"], "Controls bass energy by shaping the sub.")
        self.assertEqual(rec["advancedTip"], "Modulate the coarse by adjusting the macro.")

    def test_rewrites_secret_sauce_workflow_step_fields(self):
        normalized = {
            "secretSauce": {
                "title": "Subby psytrance bass",
                "workflowSteps": [
                    {
                        "step": 1,
                        "instruction": "Carve the room by removes the wash.",
                        "measurementJustification": "Sub-bass mono ensures stability by tightens correlation.",
                    }
                ],
            }
        }
        _apply_phase2_grammar_fixes(normalized)
        step = normalized["secretSauce"]["workflowSteps"][0]
        self.assertEqual(step["instruction"], "Carve the room by removing the wash.")
        self.assertEqual(
            step["measurementJustification"],
            "Sub-bass mono ensures stability by tightening correlation.",
        )

    def test_no_op_on_empty_normalized(self):
        normalized = {}
        # Must not raise.
        _apply_phase2_grammar_fixes(normalized)
        self.assertEqual(normalized, {})

    def test_no_op_on_already_correct_text(self):
        normalized = {
            "mixAndMasterChain": [
                {
                    "order": 1,
                    "device": "Glue Compressor",
                    "reason": "Shapes drum impact by recreating the THD measurement.",
                }
            ]
        }
        original_reason = normalized["mixAndMasterChain"][0]["reason"]
        _apply_phase2_grammar_fixes(normalized)
        self.assertEqual(
            normalized["mixAndMasterChain"][0]["reason"], original_reason
        )

    def test_handles_missing_inner_fields_gracefully(self):
        normalized = {
            "mixAndMasterChain": [
                {"order": 1, "device": "Drum Buss"},  # no reason key
                "not-a-dict",
                None,
            ],
            "abletonRecommendations": [
                {"device": "Operator", "reason": None},  # reason is None
            ],
            "secretSauce": {
                "workflowSteps": "not-a-list",
            },
        }
        # Must not raise.
        _apply_phase2_grammar_fixes(normalized)


if __name__ == "__main__":
    unittest.main()
