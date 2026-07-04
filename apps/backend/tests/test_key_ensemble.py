import unittest
from unittest import mock

import numpy as np

import analyze_core


class KeyEnsembleTests(unittest.TestCase):
    def _fake_extractor(self, table):
        """Return a KeyExtractor stand-in whose output depends on profileType."""
        def factory(profileType="edma"):
            key, scale, strength = table[profileType]
            return lambda mono: (key, scale, strength)
        return factory

    def test_ensemble_records_agreement_and_alternates(self) -> None:
        table = {
            "edma": ("C", "major", 0.90),
            "temperley": ("C", "major", 0.85),   # agrees
            "krumhansl": ("A", "minor", 0.70),    # relative -> alternate
        }
        with mock.patch.object(analyze_core.es, "KeyExtractor", self._fake_extractor(table)):
            ensemble = analyze_core._build_key_ensemble(np.zeros(4096, dtype=np.float32), "C Major")
        self.assertEqual(ensemble["method"], "profile_vote.v1")
        self.assertEqual(ensemble["agreement"], 2)  # edma + temperley
        self.assertEqual([p["profile"] for p in ensemble["profiles"]], ["edma", "temperley", "krumhansl"])
        self.assertEqual(ensemble["alternates"], [{"key": "A Minor", "strength": 0.7}])

    def test_full_key_result_carries_ensemble_but_not_fast(self) -> None:
        table = {p: ("F", "minor", 0.8) for p in ("edma", "temperley", "krumhansl")}
        with mock.patch.object(analyze_core.es, "KeyExtractor", self._fake_extractor(table)):
            full = analyze_core.analyze_key(np.zeros(4096, dtype=np.float32), include_tuning=True)
            fast = analyze_core.analyze_key(np.zeros(4096, dtype=np.float32), include_tuning=False)
        # Shipped key stays EDMA-derived; ensemble is additive and full-only.
        self.assertEqual(full["key"], "F Minor")
        self.assertEqual(full["keyProfile"], "edma")
        self.assertEqual(full["keyEnsemble"]["agreement"], 3)
        self.assertNotIn("keyEnsemble", fast)

    def test_all_profiles_failing_yields_none(self) -> None:
        def boom(profileType="edma"):
            def run(mono):
                raise RuntimeError("extractor down")
            return run
        with mock.patch.object(analyze_core.es, "KeyExtractor", boom):
            self.assertIsNone(analyze_core._build_key_ensemble(np.zeros(4096, dtype=np.float32), "C Major"))


if __name__ == "__main__":
    unittest.main()
