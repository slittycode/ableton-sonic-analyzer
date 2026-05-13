"""Unit tests for csv_export serializers and the dot-path resolver.

The route tests in test_server.py exercise the HTTP layer end-to-end;
these tests focus on the pure-logic surface of csv_export.py: given a
specific input shape for a specific field, does the CSV come out right?

The shapes we feed in here are the same shapes that
``analysis_runtime.get_run(...)["stages"]["measurement"]["result"]``
produces. If the analyzer ever drops a field or changes the per-point
key names, these tests fail loudly — that's the early-warning we want.
"""

import importlib.util
import sys
import unittest
from pathlib import Path


_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


_SPEC = importlib.util.spec_from_file_location(
    "csv_export_test", _BACKEND_ROOT / "csv_export.py"
)
if _SPEC is None or _SPEC.loader is None:
    raise AssertionError("Could not load csv_export.py")
csv_export = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(csv_export)


class RegistryTests(unittest.TestCase):
    """The registry is the public contract for which fields are exportable."""

    def test_supported_fields_v1(self):
        self.assertEqual(
            csv_export.list_supported_fields(),
            [
                "lufsCurve.momentary",
                "lufsCurve.shortTerm",
                "rhythmDetail.tempoCurve",
                "spectralBalanceTimeSeries",
            ],
        )

    def test_is_supported_field_membership(self):
        self.assertTrue(csv_export.is_supported_field("lufsCurve.shortTerm"))
        self.assertFalse(csv_export.is_supported_field("bpm"))
        self.assertFalse(csv_export.is_supported_field("lufsCurve"))  # not a leaf
        self.assertFalse(csv_export.is_supported_field(""))
        self.assertFalse(csv_export.is_supported_field("nope.nope.nope"))


class DotPathResolverTests(unittest.TestCase):
    """Verifies the simple nested-key descent — not JSONPath."""

    def test_single_key(self):
        self.assertEqual(
            csv_export._resolve_dot_path({"bpm": 128}, "bpm"), 128
        )

    def test_nested_keys(self):
        payload = {"a": {"b": {"c": 42}}}
        self.assertEqual(csv_export._resolve_dot_path(payload, "a.b.c"), 42)

    def test_missing_intermediate_returns_none(self):
        self.assertIsNone(
            csv_export._resolve_dot_path({"a": {"b": 1}}, "a.c.d")
        )

    def test_none_intermediate_returns_none(self):
        self.assertIsNone(
            csv_export._resolve_dot_path({"a": None}, "a.b")
        )

    def test_non_dict_intermediate_returns_none(self):
        self.assertIsNone(
            csv_export._resolve_dot_path({"a": [1, 2]}, "a.b")
        )


class ExportFieldToCsvTopLevelTests(unittest.TestCase):
    """Top-level routing: unknown fields and null inputs all return None."""

    def test_unknown_field_returns_none(self):
        result = csv_export.export_field_to_csv({}, "nope")
        self.assertIsNone(result)

    def test_null_measurement_returns_none(self):
        result = csv_export.export_field_to_csv(None, "lufsCurve.shortTerm")
        self.assertIsNone(result)

    def test_missing_field_returns_none(self):
        result = csv_export.export_field_to_csv({}, "lufsCurve.shortTerm")
        self.assertIsNone(result)

    def test_empty_array_returns_none_for_lufs_curve(self):
        payload = {"lufsCurve": {"shortTerm": []}}
        result = csv_export.export_field_to_csv(payload, "lufsCurve.shortTerm")
        self.assertIsNone(result)

    def test_empty_array_returns_none_for_tempo_curve(self):
        payload = {"rhythmDetail": {"tempoCurve": []}}
        result = csv_export.export_field_to_csv(payload, "rhythmDetail.tempoCurve")
        self.assertIsNone(result)

    def test_empty_array_returns_none_for_spectral_balance(self):
        payload = {"spectralBalanceTimeSeries": []}
        result = csv_export.export_field_to_csv(payload, "spectralBalanceTimeSeries")
        self.assertIsNone(result)


class FiniteFloatHelperTests(unittest.TestCase):
    """_as_finite_float guards against NaN/Inf leaking into CSV cells.

    Python's json.loads accepts NaN/Infinity by default (non-standard JSON
    extension), so a pathological analyzer output could in principle put
    a NaN into the snapshot. Without this guard, float() would happily
    convert NaN/Inf to themselves and the CSV writer would emit \"nan\"
    or \"inf\" as a string — which most downstream tools mis-parse.
    """

    def test_none_returns_none(self):
        self.assertIsNone(csv_export._as_finite_float(None))

    def test_normal_int_returns_float(self):
        self.assertEqual(csv_export._as_finite_float(42), 42.0)

    def test_normal_float_returns_self(self):
        self.assertEqual(csv_export._as_finite_float(-23.5), -23.5)

    def test_nan_returns_none(self):
        self.assertIsNone(csv_export._as_finite_float(float("nan")))

    def test_positive_inf_returns_none(self):
        self.assertIsNone(csv_export._as_finite_float(float("inf")))

    def test_negative_inf_returns_none(self):
        self.assertIsNone(csv_export._as_finite_float(float("-inf")))

    def test_non_numeric_string_returns_none(self):
        self.assertIsNone(csv_export._as_finite_float("not-a-number"))

    def test_numeric_string_is_coerced(self):
        # We don't expect strings in the analyzer payload, but if one
        # sneaks in and it's numeric, this is the same forgiving behavior
        # float() always had.
        self.assertEqual(csv_export._as_finite_float("3.14"), 3.14)


class NonFiniteValueHandlingTests(unittest.TestCase):
    """End-to-end: a row with any NaN/Inf field is skipped from the CSV."""

    def test_lufs_curve_skips_nan_lufs(self):
        payload = {
            "lufsCurve": {
                "shortTerm": [
                    {"t": 0.0, "lufs": -23.0},
                    {"t": 0.1, "lufs": float("nan")},  # skipped
                    {"t": 0.2, "lufs": -22.0},
                ]
            }
        }
        result = csv_export.export_field_to_csv(payload, "lufsCurve.shortTerm")
        self.assertIsNotNone(result)
        self.assertNotIn("nan", result)
        self.assertNotIn("NaN", result)
        # header + 2 valid rows
        self.assertEqual(len(result.strip().split("\n")), 3)

    def test_lufs_curve_skips_inf_time(self):
        payload = {
            "lufsCurve": {
                "shortTerm": [
                    {"t": float("inf"), "lufs": -23.0},  # skipped
                    {"t": 0.5, "lufs": -22.0},
                ]
            }
        }
        result = csv_export.export_field_to_csv(payload, "lufsCurve.shortTerm")
        self.assertNotIn("inf", result.lower())
        self.assertEqual(len(result.strip().split("\n")), 2)  # header + 1

    def test_tempo_curve_skips_nan_bpm(self):
        payload = {
            "rhythmDetail": {
                "tempoCurve": [
                    {"t": 0.0, "bpm": float("nan")},  # skipped
                    {"t": 1.0, "bpm": 128.0},
                ]
            }
        }
        result = csv_export.export_field_to_csv(payload, "rhythmDetail.tempoCurve")
        self.assertNotIn("nan", result.lower())
        self.assertEqual(len(result.strip().split("\n")), 2)

    def test_spectral_balance_skips_row_with_nan_band(self):
        payload = {
            "spectralBalanceTimeSeries": [
                {
                    "t": 0.0,
                    "subBass": 0.5,
                    "lowBass": 0.5,
                    "lowMids": 0.5,
                    "mids": 0.5,
                    "upperMids": 0.5,
                    "highs": 0.5,
                    "brilliance": float("nan"),  # one bad band → row skipped
                },
                {
                    "t": 1.0,
                    "subBass": 0.4,
                    "lowBass": 0.4,
                    "lowMids": 0.4,
                    "mids": 0.4,
                    "upperMids": 0.4,
                    "highs": 0.4,
                    "brilliance": 0.4,
                },
            ]
        }
        result = csv_export.export_field_to_csv(
            payload, "spectralBalanceTimeSeries"
        )
        self.assertNotIn("nan", result.lower())
        self.assertEqual(len(result.strip().split("\n")), 2)  # header + 1


class LufsCurveShortTermTests(unittest.TestCase):
    """lufsCurve.shortTerm → time,duration,lufs with duration=3.0 constant."""

    def test_basic_three_points(self):
        payload = {
            "lufsCurve": {
                "shortTerm": [
                    {"t": 0.0, "lufs": -23.0},
                    {"t": 0.1, "lufs": -22.5},
                    {"t": 0.2, "lufs": -22.0},
                ]
            }
        }
        result = csv_export.export_field_to_csv(payload, "lufsCurve.shortTerm")
        self.assertIsNotNone(result)
        lines = result.strip().split("\n")
        self.assertEqual(lines[0], "time,duration,lufs")
        self.assertEqual(len(lines), 4)  # header + 3 rows
        # First data row — exact format
        self.assertEqual(lines[1], "0.000000,3.0,-23.00")

    def test_duration_column_is_3_0_for_short_term(self):
        payload = {
            "lufsCurve": {
                "shortTerm": [{"t": 1.5, "lufs": -20.0}],
            }
        }
        result = csv_export.export_field_to_csv(payload, "lufsCurve.shortTerm")
        lines = result.strip().split("\n")
        # Column order: time,duration,lufs — duration is column 1
        cells = lines[1].split(",")
        self.assertEqual(cells[1], "3.0")

    def test_skips_points_with_missing_keys(self):
        payload = {
            "lufsCurve": {
                "shortTerm": [
                    {"t": 0.0, "lufs": -23.0},
                    {"t": 0.1},  # missing lufs — skipped
                    {"lufs": -22.0},  # missing t — skipped
                    {"t": 0.3, "lufs": -22.5},
                ]
            }
        }
        result = csv_export.export_field_to_csv(payload, "lufsCurve.shortTerm")
        lines = result.strip().split("\n")
        # header + 2 valid rows
        self.assertEqual(len(lines), 3)

    def test_all_points_invalid_returns_none(self):
        payload = {
            "lufsCurve": {
                "shortTerm": [
                    {"t": 0.0},  # missing lufs
                    {"lufs": -23.0},  # missing t
                ]
            }
        }
        result = csv_export.export_field_to_csv(payload, "lufsCurve.shortTerm")
        self.assertIsNone(result)


class LufsCurveMomentaryTests(unittest.TestCase):
    """lufsCurve.momentary → time,duration,lufs with duration=0.4 constant."""

    def test_duration_column_is_0_4_for_momentary(self):
        payload = {
            "lufsCurve": {
                "momentary": [{"t": 0.5, "lufs": -18.0}],
            }
        }
        result = csv_export.export_field_to_csv(payload, "lufsCurve.momentary")
        lines = result.strip().split("\n")
        cells = lines[1].split(",")
        self.assertEqual(cells[1], "0.4")

    def test_short_term_and_momentary_are_independent(self):
        """A run with only the momentary curve populated must still export it."""
        payload = {
            "lufsCurve": {
                "shortTerm": None,
                "momentary": [{"t": 0.0, "lufs": -25.0}],
            }
        }
        self.assertIsNone(
            csv_export.export_field_to_csv(payload, "lufsCurve.shortTerm")
        )
        result_m = csv_export.export_field_to_csv(payload, "lufsCurve.momentary")
        self.assertIsNotNone(result_m)
        self.assertIn("-25.00", result_m)


class TempoCurveTests(unittest.TestCase):
    """rhythmDetail.tempoCurve → time,bpm (no duration column)."""

    def test_basic_two_points(self):
        payload = {
            "rhythmDetail": {
                "tempoCurve": [
                    {"t": 0.0, "bpm": 128.0},
                    {"t": 10.0, "bpm": 130.5},
                ]
            }
        }
        result = csv_export.export_field_to_csv(payload, "rhythmDetail.tempoCurve")
        lines = result.strip().split("\n")
        self.assertEqual(lines[0], "time,bpm")
        self.assertEqual(len(lines), 3)
        self.assertEqual(lines[1], "0.000000,128.000")
        self.assertEqual(lines[2], "10.000000,130.500")

    def test_null_tempo_curve_returns_none(self):
        payload = {"rhythmDetail": {"tempoCurve": None}}
        result = csv_export.export_field_to_csv(payload, "rhythmDetail.tempoCurve")
        self.assertIsNone(result)


class SpectralBalanceTimeSeriesTests(unittest.TestCase):
    """spectralBalanceTimeSeries → time + 7 band columns."""

    BANDS = (
        "subBass",
        "lowBass",
        "lowMids",
        "mids",
        "upperMids",
        "highs",
        "brilliance",
    )

    def _point(self, t: float) -> dict:
        return {"t": t, **{band: 0.5 for band in self.BANDS}}

    def test_columns_match_band_order(self):
        payload = {"spectralBalanceTimeSeries": [self._point(0.0)]}
        result = csv_export.export_field_to_csv(payload, "spectralBalanceTimeSeries")
        lines = result.strip().split("\n")
        self.assertEqual(
            lines[0],
            "time,subBass,lowBass,lowMids,mids,upperMids,highs,brilliance",
        )

    def test_row_has_eight_cells(self):
        payload = {"spectralBalanceTimeSeries": [self._point(1.0)]}
        result = csv_export.export_field_to_csv(payload, "spectralBalanceTimeSeries")
        lines = result.strip().split("\n")
        cells = lines[1].split(",")
        self.assertEqual(len(cells), 8)  # time + 7 bands

    def test_row_with_missing_band_is_skipped(self):
        payload = {
            "spectralBalanceTimeSeries": [
                self._point(0.0),
                {"t": 1.0, "subBass": 0.1},  # missing 6 bands — skipped
                self._point(2.0),
            ]
        }
        result = csv_export.export_field_to_csv(payload, "spectralBalanceTimeSeries")
        lines = result.strip().split("\n")
        # header + 2 valid rows
        self.assertEqual(len(lines), 3)


if __name__ == "__main__":
    unittest.main()
