"""
Integration tests using JSON fixtures.

Tests that parsers can handle real API responses from fixtures.
"""

import unittest
import json
from pathlib import Path

from tray_prusa.adapters import (
    parse_prusalink_state,
    parse_octoprint_state,
    parse_prusa_connect_state,
)
from tray_prusa.models import PrinterStatus


class TestFixtures(unittest.TestCase):
    """Test parsers with real API response fixtures."""

    @classmethod
    def setUpClass(cls):
        """Load all fixtures."""
        fixtures_dir = Path(__file__).parent / "fixtures"

        # Load PrusaLink fixtures
        with open(fixtures_dir / "prusalink_v1_status_printing.json") as f:
            cls.prusalink_v1 = json.load(f)

        with open(fixtures_dir / "prusalink_legacy_job_printing.json") as f:
            cls.prusalink_legacy = json.load(f)

        # Load OctoPrint fixture
        with open(fixtures_dir / "octoprint_job_printing.json") as f:
            cls.octoprint = json.load(f)

        # Load PrusaConnect fixture
        with open(fixtures_dir / "prusaconnect_status_sample.json") as f:
            cls.prusaconnect = json.load(f)

    def test_prusalink_v1_fixture(self):
        """Test PrusaLink v1 status fixture."""
        state = parse_prusalink_state(self.prusalink_v1)

        self.assertEqual(state.status, PrinterStatus.PRINTING)
        self.assertIsNotNone(state.progress)
        self.assertAlmostEqual(state.progress, 0.425, places=3)
        self.assertEqual(state.eta_seconds, 1847)
        self.assertEqual(state.nozzle_temp, 215.0)
        self.assertEqual(state.bed_temp, 60.0)
        self.assertEqual(state.job_name, "benchy.gcode")

    def test_prusalink_legacy_fixture(self):
        """Test PrusaLink legacy /api/job fixture."""
        state = parse_prusalink_state(self.prusalink_legacy)

        self.assertEqual(state.status, PrinterStatus.PRINTING)
        self.assertIsNotNone(state.progress)
        self.assertAlmostEqual(state.progress, 0.675, places=3)
        self.assertEqual(state.eta_seconds, 1170)
        self.assertEqual(state.job_name, "calibration_cube.gcode")
        # Legacy format has temps in different structure
        self.assertIsNotNone(state.nozzle_temp)
        self.assertIsNotNone(state.bed_temp)

    def test_octoprint_fixture(self):
        """Test OctoPrint /api/job fixture."""
        state = parse_octoprint_state(self.octoprint)

        self.assertEqual(state.status, PrinterStatus.PRINTING)
        self.assertIsNotNone(state.progress)
        self.assertAlmostEqual(state.progress, 0.425, places=3)
        self.assertEqual(state.eta_seconds, 4140)
        self.assertEqual(state.job_name, "large_print.gcode")
        self.assertEqual(state.nozzle_temp, 210.2)
        self.assertEqual(state.bed_temp, 59.5)

    def test_prusaconnect_fixture(self):
        """Test PrusaConnect status fixture."""
        state = parse_prusa_connect_state(self.prusaconnect)

        self.assertEqual(state.status, PrinterStatus.PRINTING)
        self.assertIsNotNone(state.progress)
        self.assertAlmostEqual(state.progress, 0.455, places=3)
        self.assertEqual(state.eta_seconds, 1800)
        self.assertEqual(state.nozzle_temp, 215.0)
        self.assertEqual(state.bed_temp, 60.0)
        self.assertEqual(state.job_name, "benchy.gcode")

    def test_all_fixtures_have_timestamp(self):
        """Test that all parsed states have timestamps."""
        states = [
            parse_prusalink_state(self.prusalink_v1),
            parse_prusalink_state(self.prusalink_legacy),
            parse_octoprint_state(self.octoprint),
            parse_prusa_connect_state(self.prusaconnect),
        ]

        for state in states:
            self.assertIsNotNone(state.last_ok_timestamp)

    def test_all_fixtures_parse_without_errors(self):
        """Test that all fixtures parse without throwing exceptions."""
        # This test just verifies no exceptions are raised
        try:
            parse_prusalink_state(self.prusalink_v1)
            parse_prusalink_state(self.prusalink_legacy)
            parse_octoprint_state(self.octoprint)
            parse_prusa_connect_state(self.prusaconnect)
        except Exception as e:
            self.fail(f"Parser raised exception: {e}")


class TestFixtureValidity(unittest.TestCase):
    """Test that fixture files are valid JSON."""

    def test_all_fixtures_are_valid_json(self):
        """Test that all fixture files contain valid JSON."""
        fixtures_dir = Path(__file__).parent / "fixtures"

        fixture_files = [
            "prusalink_v1_status_printing.json",
            "prusalink_legacy_job_printing.json",
            "octoprint_job_printing.json",
            "prusaconnect_status_sample.json",
        ]

        for filename in fixture_files:
            filepath = fixtures_dir / filename
            self.assertTrue(filepath.exists(), f"Fixture not found: {filename}")

            with open(filepath) as f:
                try:
                    data = json.load(f)
                    self.assertIsInstance(
                        data, dict, f"{filename} should contain a JSON object"
                    )
                except json.JSONDecodeError as e:
                    self.fail(f"{filename} contains invalid JSON: {e}")


if __name__ == "__main__":
    unittest.main()
