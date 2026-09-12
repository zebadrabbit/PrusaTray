"""
Integration tests using JSON fixtures.

Tests that parsers can handle real API responses from fixtures.
"""

import unittest
import json
from pathlib import Path

from tray_prusa.adapters import (
    parse_prusalink_state,
    parse_prusalink_job_name,
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

        with open(fixtures_dir / "prusalink_v1_job.json") as f:
            cls.prusalink_v1_job = json.load(f)

        with open(fixtures_dir / "prusalink_v1_status_attention.json") as f:
            cls.prusalink_v1_attention = json.load(f)

        with open(fixtures_dir / "prusalink_legacy_job_printing.json") as f:
            cls.prusalink_legacy = json.load(f)

        # Load OctoPrint fixture
        with open(fixtures_dir / "octoprint_job_printing.json") as f:
            cls.octoprint = json.load(f)

        # Load Prusa Connect fixtures
        with open(fixtures_dir / "prusaconnect_printer.json") as f:
            cls.connect_printer = json.load(f)

        with open(fixtures_dir / "prusaconnect_jobs.json") as f:
            cls.connect_jobs = json.load(f)

    def test_prusalink_v1_fixture(self):
        """Test PrusaLink v1 status fixture."""
        state = parse_prusalink_state(self.prusalink_v1)

        self.assertEqual(state.status, PrinterStatus.PRINTING)
        self.assertIsNotNone(state.progress)
        self.assertAlmostEqual(state.progress, 0.425, places=3)
        self.assertEqual(state.eta_seconds, 1847)
        self.assertEqual(state.nozzle_temp, 214.9)
        self.assertEqual(state.bed_temp, 59.5)
        # /api/v1/status carries no file name at all.
        self.assertIsNone(state.job_name)

    def test_prusalink_v1_job_name_from_job_endpoint(self):
        """Job name comes from /api/v1/job and is passed into the status parse."""
        name = parse_prusalink_job_name(self.prusalink_v1_job)
        self.assertEqual(name, "benchy.bgcode")  # display_name beats the 8.3 name

        state = parse_prusalink_state(self.prusalink_v1, job_name=name)
        self.assertEqual(state.job_name, "benchy.bgcode")

    def test_prusalink_v1_attention_fixture(self):
        """ATTENTION maps to its own status and surfaces the printer message."""
        state = parse_prusalink_state(self.prusalink_v1_attention)

        self.assertEqual(state.status, PrinterStatus.ATTENTION)
        self.assertEqual(state.message, "Filament runout")
        # time_remaining of -1 means "no estimate yet", not an ETA.
        self.assertIsNone(state.eta_seconds)

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
        """Test Prusa Connect printer + jobs fixtures."""
        state = parse_prusa_connect_state(self.connect_printer, self.connect_jobs[0])

        self.assertEqual(state.status, PrinterStatus.PRINTING)
        self.assertIsNotNone(state.progress)
        self.assertAlmostEqual(state.progress, 0.425, places=3)
        self.assertEqual(state.nozzle_temp, 214.9)
        self.assertEqual(state.bed_temp, 59.5)
        self.assertEqual(state.job_name, "benchy.bgcode")

    def test_prusaconnect_without_job(self):
        """A printer with no running job reports no progress."""
        state = parse_prusa_connect_state(self.connect_printer, None)

        self.assertEqual(state.status, PrinterStatus.PRINTING)
        self.assertIsNone(state.progress)
        self.assertIsNone(state.job_name)
        self.assertEqual(state.nozzle_temp, 214.9)

    def test_all_fixtures_have_timestamp(self):
        """Test that all parsed states have timestamps."""
        states = [
            parse_prusalink_state(self.prusalink_v1),
            parse_prusalink_state(self.prusalink_legacy),
            parse_octoprint_state(self.octoprint),
            parse_prusa_connect_state(self.connect_printer, self.connect_jobs[0]),
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
            parse_prusa_connect_state(self.connect_printer, self.connect_jobs[0])
        except Exception as e:
            self.fail(f"Parser raised exception: {e}")


class TestFixtureValidity(unittest.TestCase):
    """Test that fixture files are valid JSON."""

    def test_all_fixtures_are_valid_json(self):
        """Test that all fixture files contain valid JSON."""
        fixtures_dir = Path(__file__).parent / "fixtures"

        for filepath in sorted(fixtures_dir.glob("*.json")):
            with open(filepath) as f:
                try:
                    json.load(f)
                except json.JSONDecodeError as e:
                    self.fail(f"{filepath.name} contains invalid JSON: {e}")


if __name__ == "__main__":
    unittest.main()
