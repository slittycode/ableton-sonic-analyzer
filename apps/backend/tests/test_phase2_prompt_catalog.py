"""Regression tests for Phase 2 prompt examples against the Live 12 catalog."""

import json
import re
import unittest
from pathlib import Path


PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"


def _load_catalog() -> dict:
    return json.loads((PROMPTS_DIR / "live12_device_catalog.json").read_text(encoding="utf-8"))


def _load_prompt() -> str:
    return (PROMPTS_DIR / "phase2_system.txt").read_text(encoding="utf-8")


def _example_cards(prompt: str) -> list[dict]:
    cards: list[dict] = []
    for match in re.finditer(r'\{"device":.*?\}', prompt):
        cards.append(json.loads(match.group(0)))
    return cards


class Phase2PromptCatalogTests(unittest.TestCase):
    def test_prompt_json_example_cards_use_catalog_parameters(self):
        catalog = _load_catalog()
        lookup = {device["name"]: device for device in catalog["devices"]}
        cards = _example_cards(_load_prompt())

        self.assertGreaterEqual(len(cards), 6)
        for card in cards:
            with self.subTest(device=card.get("device"), parameter=card.get("parameter")):
                device = card["device"]
                parameter = card["parameter"]
                self.assertIn(device, lookup)
                entry = lookup[device]
                aliases = entry.get("parameterAliases") or {}
                canonical = aliases.get(parameter, parameter)
                self.assertIn(canonical, entry["allowedParameters"])

    def test_prompt_blocks_old_invalid_parameter_strings(self):
        prompt = _load_prompt()

        self.assertNotIn('"parameter":"Envelope Decay"', prompt)
        self.assertNotIn("Reverb device PreDelay parameter", prompt)
        self.assertNotIn("Set Reverb PreDelay", prompt)
        self.assertIn('"parameter":"Amp Envelope Decay"', prompt)
        self.assertIn("Reverb device Predelay parameter", prompt)

    def test_prompt_loudness_units_are_v2_dbtp_with_plr_and_bpm_hedge(self):
        """WS2: the prompt must teach Phase 1 v2 loudness semantics.

        truePeak is dBTP (not a linear proxy), the mastering move is driven by
        the now-correct plr, and the tempo hedge uses the v2 normalized 0.4
        bpmConfidence threshold (matching phase2Validator's shared threshold).
        """
        prompt = _load_prompt()

        # v2: truePeak is dBTP. The old linear framing (1.0 == full scale,
        # >1.0 == over) would mislead Gemini now that >0.0 dBTP is the over.
        self.assertNotIn("linear amplitude proxy", prompt)
        self.assertIn("above 0.0 dBTP", prompt)

        # PLR-driven mastering decision bands surface the now-correct plr.
        self.assertIn("peak-to-loudness ratio", prompt)
        self.assertIn("PLR ≤ 8 LU", prompt)

        # bpmConfidence hedge at the v2 normalized 0.4 threshold.
        self.assertIn("bpmConfidence < 0.4", prompt)


if __name__ == "__main__":
    unittest.main()
