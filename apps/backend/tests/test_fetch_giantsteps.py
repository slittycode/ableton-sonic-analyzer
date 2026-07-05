"""Regression tests for scripts/fetch_giantsteps.py annotation staging.

The GiantSteps key/tempo repos ship each track's annotation twice with
identical content: a plain single-value file under ``annotations/<subset>/``
("D minor" / "137.5") and a MIREX-format file under ``annotations/giantsteps/``
whose first line is a ``#@format:`` header. The evaluation harness expects the
plain form — the header form's first token parses as the note name "#@format:"
and silently scores every clip 0.0 (a vacuous "evaluated" run). These tests
pin that staging always emits the plain, harness-parseable form.
"""

import tempfile
import unittest
from pathlib import Path

from fundamentals_evaluation import _parse_key_pc
from scripts.fetch_giantsteps import (
    _annotation_stems,
    _is_plain_annotation,
    _stage_annotations,
)

# The exact MIREX-format annotation the upstream giantsteps/ directory ships.
_MIREX_KEY = "#@format: key\ttimestamp(float)\tkey(string)\nkey 0 D minor\n"
_PLAIN_KEY = "D minor"


def _make_dual_format_repo(repo_dir: Path) -> None:
    """A repo that ships one stem in both plain and MIREX form, plus a plain-only stem."""
    plain = repo_dir / "annotations" / "key"
    mirex = repo_dir / "annotations" / "giantsteps"
    plain.mkdir(parents=True)
    mirex.mkdir(parents=True)
    (plain / "111.LOFI.key").write_text(_PLAIN_KEY, encoding="utf-8")
    (mirex / "111.LOFI.key").write_text(_MIREX_KEY, encoding="utf-8")
    (plain / "222.LOFI.key").write_text("Ab major", encoding="utf-8")


class FetchGiantstepsStagingTests(unittest.TestCase):
    def test_stages_plain_format_not_mirex_header(self) -> None:
        with tempfile.TemporaryDirectory(prefix="asa_gs_stage_") as tmp:
            root = Path(tmp)
            repo = root / "_repos" / "giantsteps-key-dataset"
            _make_dual_format_repo(repo)

            staged = _stage_annotations(repo, root / "key", "key")
            self.assertEqual(staged, 2)  # one file per stem, de-duplicated

            content = (root / "key" / "annotations" / "111.LOFI.key").read_text(encoding="utf-8")
            self.assertNotIn("#@format", content)
            # The whole staged file must parse to a real key, the way the harness reads it.
            self.assertEqual(_parse_key_pc(content.strip()), (2, "minor"))  # D minor

    def test_annotation_stems_are_deduplicated(self) -> None:
        with tempfile.TemporaryDirectory(prefix="asa_gs_stems_") as tmp:
            repo = Path(tmp) / "_repos" / "giantsteps-key-dataset"
            _make_dual_format_repo(repo)
            self.assertEqual(_annotation_stems(repo, "key"), ["111.LOFI", "222.LOFI"])

    def test_is_plain_annotation_detects_header(self) -> None:
        with tempfile.TemporaryDirectory(prefix="asa_gs_plain_") as tmp:
            root = Path(tmp)
            plain = root / "plain.key"
            mirex = root / "mirex.key"
            plain.write_text(_PLAIN_KEY, encoding="utf-8")
            mirex.write_text(_MIREX_KEY, encoding="utf-8")
            self.assertTrue(_is_plain_annotation(plain))
            self.assertFalse(_is_plain_annotation(mirex))


if __name__ == "__main__":
    unittest.main()
