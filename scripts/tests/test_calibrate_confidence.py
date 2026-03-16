"""
Tests for confidence calibration script.

TDD Workflow:
1. Write test - verify FAIL
2. Implement calibrate_confidence.py
3. Run test - verify PASS
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

# Add parent directory to path to import calibrate_confidence
sys.path.insert(0, str(Path(__file__).parent.parent))

import calibrate_confidence as calib


class TestGroundTruthLoading(unittest.TestCase):
    """Test ground truth loading functionality."""

    def test_load_ground_truth_success(self):
        """Test successful loading of ground truth JSON."""
        mock_data = {
            "track_01": {
                "genre": "Techno",
                "bpm": 128,
                "key": "Am",
                "has_sidechain": True,
                "melody_accuracy": "high",
                "chord_accuracy": "low"
            }
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(mock_data, f)
            temp_path = f.name

        try:
            result = calib.load_ground_truth(temp_path)
            self.assertEqual(result["track_01"]["genre"], "Techno")
            self.assertEqual(result["track_01"]["has_sidechain"], True)
            self.assertEqual(result["track_01"]["melody_accuracy"], "high")
        finally:
            os.unlink(temp_path)

    def test_load_ground_truth_file_not_found(self):
        """Test handling of missing ground truth file."""
        result = calib.load_ground_truth("/nonexistent/path/labels.json")
        self.assertEqual(result, {})

    def test_load_ground_truth_invalid_json(self):
        """Test handling of invalid JSON."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("invalid json{}")
            temp_path = f.name

        try:
            result = calib.load_ground_truth(temp_path)
            self.assertEqual(result, {})
        finally:
            os.unlink(temp_path)


class TestAnalysisResultsLoading(unittest.TestCase):
    """Test cached analysis results loading."""

    def test_load_cached_results_success(self):
        """Test loading cached analysis results."""
        mock_result = {
            "bpm": 128.5,
            "melodyDetail": {"pitchConfidence": 0.75},
            "chordDetail": {"chordStrength": 0.82},
            "sidechainDetail": {"pumpingConfidence": 0.45}
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(mock_result, f)
            temp_path = f.name

        try:
            result = calib.load_cached_result(temp_path)
            self.assertEqual(result["bpm"], 128.5)
            self.assertEqual(result["melodyDetail"]["pitchConfidence"], 0.75)
        finally:
            os.unlink(temp_path)

    def test_load_cached_results_not_found(self):
        """Test handling of missing cached results."""
        result = calib.load_cached_result("/nonexistent/result.json")
        self.assertIsNone(result)


class TestConfidenceExtraction(unittest.TestCase):
    """Test extraction of confidence values from analysis results."""

    def test_extract_pitch_confidence(self):
        """Test extraction of pitch confidence from melody detail."""
        analysis = {"melodyDetail": {"pitchConfidence": 0.65}}
        self.assertEqual(calib.extract_pitch_confidence(analysis), 0.65)

    def test_extract_pitch_confidence_missing(self):
        """Test extraction when melodyDetail is None."""
        analysis = {"melodyDetail": None}
        self.assertIsNone(calib.extract_pitch_confidence(analysis))

    def test_extract_pitch_confidence_no_key(self):
        """Test extraction when pitchConfidence key is missing."""
        analysis = {"melodyDetail": {}}
        self.assertIsNone(calib.extract_pitch_confidence(analysis))

    def test_extract_chord_strength(self):
        """Test extraction of chord strength from chord detail."""
        analysis = {"chordDetail": {"chordStrength": 0.75}}
        self.assertEqual(calib.extract_chord_strength(analysis), 0.75)

    def test_extract_chord_strength_missing(self):
        """Test extraction when chordDetail is None."""
        analysis = {"chordDetail": None}
        self.assertIsNone(calib.extract_chord_strength(analysis))

    def test_extract_pumping_confidence(self):
        """Test extraction of pumping confidence from sidechain detail."""
        analysis = {"sidechainDetail": {"pumpingConfidence": 0.55}}
        self.assertEqual(calib.extract_pumping_confidence(analysis), 0.55)

    def test_extract_pumping_confidence_missing(self):
        """Test extraction when sidechainDetail is None."""
        analysis = {"sidechainDetail": None}
        self.assertIsNone(calib.extract_pumping_confidence(analysis))


class TestMetricsCalculation(unittest.TestCase):
    """Test precision, recall, and F1 calculation."""

    def test_calculate_metrics_perfect(self):
        """Test metrics with perfect predictions."""
        # All flagged are actually positive (TP=2), none missed (FN=0), no false alarms (FP=0)
        y_true = [True, True, False, False]
        y_pred = [True, True, False, False]
        metrics = calib.calculate_metrics(y_true, y_pred)
        self.assertEqual(metrics["precision"], 1.0)
        self.assertEqual(metrics["recall"], 1.0)
        self.assertEqual(metrics["f1"], 1.0)

    def test_calculate_metrics_zero_precision(self):
        """Test metrics with no true positives."""
        y_true = [False, False, True, True]
        y_pred = [True, True, False, False]
        metrics = calib.calculate_metrics(y_true, y_pred)
        self.assertEqual(metrics["precision"], 0.0)
        self.assertEqual(metrics["recall"], 0.0)
        self.assertEqual(metrics["f1"], 0.0)

    def test_calculate_metrics_partial(self):
        """Test metrics with partial correctness."""
        y_true = [True, True, False, False]
        y_pred = [True, False, True, False]
        metrics = calib.calculate_metrics(y_true, y_pred)
        # TP=1, FP=1, FN=1
        # Precision = 1/2 = 0.5
        # Recall = 1/2 = 0.5
        # F1 = 2*(0.5*0.5)/(0.5+0.5) = 0.5
        self.assertEqual(metrics["precision"], 0.5)
        self.assertEqual(metrics["recall"], 0.5)
        self.assertEqual(metrics["f1"], 0.5)

    def test_calculate_metrics_empty(self):
        """Test metrics with empty inputs."""
        metrics = calib.calculate_metrics([], [])
        self.assertEqual(metrics["precision"], 0.0)
        self.assertEqual(metrics["recall"], 0.0)
        self.assertEqual(metrics["f1"], 0.0)


class TestThresholdEvaluation(unittest.TestCase):
    """Test threshold evaluation for each metric type."""

    def test_evaluate_pitch_threshold(self):
        """Test pitch confidence threshold evaluation."""
        # Track: (pitch_confidence, melody_accuracy)
        # melody_accuracy "high" = good, "low" = bad (should be flagged)
        tracks = [
            ("track1", 0.2, "high"),   # High conf, high accuracy (OK)
            ("track2", 0.1, "low"),    # Low conf, low accuracy (should flag, correct)
            ("track3", 0.2, "low"),    # High conf, low accuracy (miss)
            ("track4", 0.1, "high"),   # Low conf, high accuracy (false alarm)
        ]

        # Threshold 0.15: flag anything below as "low quality"
        result = calib.evaluate_pitch_threshold(tracks, 0.15)
        # TP: track2 flagged as low, actually low
        # FP: track4 flagged as low, actually high
        # FN: track3 not flagged, actually low
        self.assertEqual(result["true_positives"], 1)
        self.assertEqual(result["false_positives"], 1)
        self.assertEqual(result["false_negatives"], 1)

    def test_evaluate_chord_threshold(self):
        """Test chord strength threshold evaluation."""
        tracks = [
            ("track1", 0.8, "high"),
            ("track2", 0.6, "low"),
            ("track3", 0.8, "low"),
            ("track4", 0.6, "high"),
        ]

        result = calib.evaluate_chord_threshold(tracks, 0.7)
        self.assertEqual(result["true_positives"], 1)  # track2 flagged correctly
        self.assertEqual(result["false_positives"], 1)  # track4 flagged incorrectly
        self.assertEqual(result["false_negatives"], 1)  # track3 missed

    def test_evaluate_sidechain_threshold(self):
        """Test pumping confidence threshold evaluation."""
        tracks = [
            ("track1", 0.5, True),
            ("track2", 0.3, False),
            ("track3", 0.5, False),
            ("track4", 0.3, True),
        ]

        result = calib.evaluate_sidechain_threshold(tracks, 0.4)
        # TP: track1 detected, has sidechain
        # FP: track3 detected, no sidechain
        # FN: track4 missed, has sidechain
        self.assertEqual(result["true_positives"], 1)
        self.assertEqual(result["false_positives"], 1)
        self.assertEqual(result["false_negatives"], 1)


class TestOptimalThresholdSelection(unittest.TestCase):
    """Test selection of optimal thresholds."""

    def test_find_optimal_threshold(self):
        """Test finding threshold with highest F1."""
        results = [
            {"threshold": 0.1, "f1": 0.6, "precision": 0.5, "recall": 0.75},
            {"threshold": 0.2, "f1": 0.8, "precision": 0.8, "recall": 0.8},
            {"threshold": 0.3, "f1": 0.7, "precision": 0.9, "recall": 0.6},
        ]
        optimal = calib.find_optimal_threshold(results)
        self.assertEqual(optimal["threshold"], 0.2)
        self.assertEqual(optimal["f1"], 0.8)

    def test_find_optimal_threshold_empty(self):
        """Test with empty results."""
        optimal = calib.find_optimal_threshold([])
        self.assertIsNone(optimal)


class TestMarkdownReportGeneration(unittest.TestCase):
    """Test markdown report generation."""

    def test_generate_report(self):
        """Test full markdown report generation."""
        calibration_results = {
            "pitch_confidence": {
                "current_threshold": 0.15,
                "tested_thresholds": [
                    {"threshold": 0.10, "precision": 0.7, "recall": 0.8, "f1": 0.75, "track_count": 8},
                    {"threshold": 0.15, "precision": 0.8, "recall": 0.75, "f1": 0.77, "track_count": 8},
                ],
                "optimal": {"threshold": 0.15, "f1": 0.77, "precision": 0.8, "recall": 0.75, "track_count": 8},
            },
            "chord_strength": {
                "current_threshold": 0.70,
                "tested_thresholds": [
                    {"threshold": 0.70, "precision": 0.75, "recall": 0.7, "f1": 0.72, "track_count": 6},
                ],
                "optimal": {"threshold": 0.70, "f1": 0.72, "precision": 0.75, "recall": 0.7, "track_count": 6},
            },
            "pumping_confidence": {
                "current_threshold": 0.40,
                "tested_thresholds": [
                    {"threshold": 0.40, "precision": 0.85, "recall": 0.8, "f1": 0.82, "track_count": 10},
                ],
                "optimal": {"threshold": 0.40, "f1": 0.82, "precision": 0.85, "recall": 0.8, "track_count": 10},
            },
        }

        report = calib.generate_markdown_report(calibration_results, track_count=5)

        # Check key sections are present
        self.assertIn("# Confidence Calibration Results", report)
        self.assertIn("Tracks analyzed: 5", report)
        self.assertIn("## Pitch Confidence (Melody)", report)
        self.assertIn("## Chord Strength", report)
        self.assertIn("## Pumping Confidence (Sidechain)", report)
        self.assertIn("| Threshold | Precision | Recall | F1 Score |", report)
        self.assertIn("## Summary of Recommendations", report)


class TestEndToEnd(unittest.TestCase):
    """End-to-end integration tests."""

    def test_main_with_mock_data(self):
        """Test main function with mock ground truth and analysis data."""
        ground_truth = {
            "track1": {
                "genre": "Techno",
                "bpm": 128,
                "key": "Am",
                "has_sidechain": True,
                "melody_accuracy": "high",
                "chord_accuracy": "high"
            },
            "track2": {
                "genre": "House",
                "bpm": 124,
                "key": "Fm",
                "has_sidechain": False,
                "melody_accuracy": "low",
                "chord_accuracy": "low"
            }
        }

        analysis_results = {
            "track1": {
                "melodyDetail": {"pitchConfidence": 0.8},
                "chordDetail": {"chordStrength": 0.85},
                "sidechainDetail": {"pumpingConfidence": 0.6}
            },
            "track2": {
                "melodyDetail": {"pitchConfidence": 0.1},
                "chordDetail": {"chordStrength": 0.5},
                "sidechainDetail": {"pumpingConfidence": 0.2}
            }
        }

        # Should run without error
        with tempfile.TemporaryDirectory() as tmpdir:
            gt_path = os.path.join(tmpdir, "labels.json")
            with open(gt_path, 'w') as f:
                json.dump(ground_truth, f)

            # Mock the analysis loading
            with patch.object(calib, 'load_cached_result') as mock_load:
                def mock_loader(track_name):
                    return analysis_results.get(track_name)
                mock_load.side_effect = lambda path: mock_loader(os.path.basename(path).replace('.json', ''))

                # Should not raise
                results = calib.run_calibration(gt_path, tmpdir)

                self.assertIn("pitch_confidence", results)
                self.assertIn("chord_strength", results)
                self.assertIn("pumping_confidence", results)


if __name__ == "__main__":
    unittest.main()
