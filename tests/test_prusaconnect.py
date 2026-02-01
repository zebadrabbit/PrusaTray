"""
Test PrusaConnect API parser.

Uses fixture JSON data only - no network calls.
"""

import unittest
from datetime import datetime
from tray_prusa.models import PrinterStatus
from tray_prusa.adapters import parse_prusa_connect_state


class TestPrusaConnectParser(unittest.TestCase):
    """Test parse_prusa_connect_state() with various response formats."""

    def test_flat_format_printing(self):
        """Test flat JSON format while printing."""
        data = {
            "state": "PRINTING",
            "progress": 45.5,
            "time_remaining": 1800,
            "temp_nozzle": 215.0,
            "temp_bed": 60.0,
            "file_name": "benchy.gcode",
        }

        state = parse_prusa_connect_state(data)

        self.assertEqual(state.status, PrinterStatus.PRINTING)
        self.assertAlmostEqual(state.progress, 0.455, places=3)
        self.assertEqual(state.eta_seconds, 1800)
        self.assertEqual(state.nozzle_temp, 215.0)
        self.assertEqual(state.bed_temp, 60.0)
        self.assertEqual(state.job_name, "benchy.gcode")
        self.assertIsNone(state.error_message)

    def test_nested_format_printing(self):
        """Test nested printer/job format."""
        data = {
            "printer": {"state": "PRINTING", "temp_nozzle": 215.0, "temp_bed": 60.0},
            "job": {
                "progress": 0.455,  # 0-1 format
                "time_remaining": 1800,
                "file_name": "calibration_cube.gcode",
            },
        }

        state = parse_prusa_connect_state(data)

        self.assertEqual(state.status, PrinterStatus.PRINTING)
        self.assertAlmostEqual(state.progress, 0.455, places=3)
        self.assertEqual(state.eta_seconds, 1800)
        self.assertEqual(state.nozzle_temp, 215.0)
        self.assertEqual(state.bed_temp, 60.0)
        self.assertEqual(state.job_name, "calibration_cube.gcode")

    def test_idle_no_job(self):
        """Test IDLE state with no active job."""
        data = {"state": "IDLE", "temp_nozzle": 25.0, "temp_bed": 23.0}

        state = parse_prusa_connect_state(data)

        self.assertEqual(state.status, PrinterStatus.IDLE)
        self.assertIsNone(state.progress)
        self.assertIsNone(state.eta_seconds)
        self.assertIsNone(state.job_name)
        self.assertEqual(state.nozzle_temp, 25.0)
        self.assertEqual(state.bed_temp, 23.0)

    def test_paused_state(self):
        """Test PAUSED state."""
        data = {
            "state": "PAUSED",
            "progress": 67.2,
            "time_remaining": 900,
            "file_name": "large_print.gcode",
        }

        state = parse_prusa_connect_state(data)

        self.assertEqual(state.status, PrinterStatus.PAUSED)
        self.assertAlmostEqual(state.progress, 0.672, places=3)
        self.assertEqual(state.eta_seconds, 900)

    def test_error_state(self):
        """Test ERROR state."""
        data = {"state": "ERROR", "temp_nozzle": 215.0, "temp_bed": 60.0}

        state = parse_prusa_connect_state(data)

        self.assertEqual(state.status, PrinterStatus.ERROR)

    def test_progress_0_to_1_format(self):
        """Test progress in 0-1 range (not 0-100)."""
        data = {"state": "PRINTING", "progress": 0.875}  # 87.5%

        state = parse_prusa_connect_state(data)

        self.assertAlmostEqual(state.progress, 0.875, places=3)

    def test_progress_0_to_100_format(self):
        """Test progress in 0-100 range (normalized to 0-1)."""
        data = {"state": "PRINTING", "progress": 87.5}  # Should be normalized to 0.875

        state = parse_prusa_connect_state(data)

        self.assertAlmostEqual(state.progress, 0.875, places=3)

    def test_progress_exactly_100(self):
        """Test progress exactly 100 (complete)."""
        data = {"state": "PRINTING", "progress": 100.0}

        state = parse_prusa_connect_state(data)

        self.assertAlmostEqual(state.progress, 1.0, places=3)

    def test_progress_exactly_1(self):
        """Test progress exactly 1.0 (complete, 0-1 format)."""
        data = {"state": "PRINTING", "progress": 1.0}

        state = parse_prusa_connect_state(data)

        self.assertAlmostEqual(state.progress, 1.0, places=3)

    def test_alternative_field_names(self):
        """Test alternative field names (filename vs file_name, etc)."""
        data = {
            "status": "PRINTING",  # "status" instead of "state"
            "job": {
                "completion": 42.5,  # "completion" instead of "progress"
                "printTimeLeft": 1500,  # camelCase instead of snake_case
                "filename": "test.gcode",  # "filename" instead of "file_name"
            },
        }

        state = parse_prusa_connect_state(data)

        self.assertEqual(state.status, PrinterStatus.PRINTING)
        self.assertAlmostEqual(state.progress, 0.425, places=3)
        self.assertEqual(state.eta_seconds, 1500)
        self.assertEqual(state.job_name, "test.gcode")

    def test_temperature_nested_format(self):
        """Test temperatures in nested format."""
        data = {"state": "PRINTING", "temperature": {"nozzle": 210.5, "bed": 59.0}}

        state = parse_prusa_connect_state(data)

        self.assertEqual(state.nozzle_temp, 210.5)
        self.assertEqual(state.bed_temp, 59.0)

    def test_temperature_octoprint_style(self):
        """Test temperatures in OctoPrint-style nested format."""
        data = {
            "state": "PRINTING",
            "temperature": {
                "tool0": {"actual": 215.3, "target": 220.0},
                "bed": {"actual": 60.2},
            },
        }

        state = parse_prusa_connect_state(data)

        self.assertEqual(state.nozzle_temp, 215.3)
        self.assertEqual(state.bed_temp, 60.2)

    def test_unknown_fields_ignored(self):
        """Test that unknown fields are ignored gracefully."""
        data = {
            "state": "PRINTING",
            "progress": 50.0,
            "unknown_field_1": "some value",
            "unknown_field_2": 12345,
            "nested_unknown": {"foo": "bar"},
        }

        # Should not raise exception
        state = parse_prusa_connect_state(data)

        self.assertEqual(state.status, PrinterStatus.PRINTING)
        self.assertAlmostEqual(state.progress, 0.5, places=3)

    def test_missing_state_field(self):
        """Test response with missing state field."""
        data = {"progress": 25.0, "temp_nozzle": 215.0}

        state = parse_prusa_connect_state(data)

        # Should default to UNKNOWN
        self.assertEqual(state.status, PrinterStatus.UNKNOWN)
        self.assertAlmostEqual(state.progress, 0.25, places=3)

    def test_file_nested_in_job(self):
        """Test file name nested in job.file.name structure."""
        data = {"state": "PRINTING", "job": {"file": {"name": "nested_file.gcode"}}}

        state = parse_prusa_connect_state(data)

        self.assertEqual(state.job_name, "nested_file.gcode")

    def test_malformed_data_error_handling(self):
        """Test error handling with completely malformed data."""
        data = {"state": None, "progress": "not a number", "temp_nozzle": None}

        # Should not crash, may return ERROR or parse what it can
        state = parse_prusa_connect_state(data)

        # At minimum should return a PrinterState
        self.assertIsNotNone(state)
        self.assertIsInstance(state.status, PrinterStatus)

    def test_empty_response(self):
        """Test empty JSON object."""
        data = {}

        state = parse_prusa_connect_state(data)

        self.assertEqual(state.status, PrinterStatus.UNKNOWN)
        self.assertIsNone(state.progress)
        self.assertIsNone(state.eta_seconds)

    def test_timestamp_populated(self):
        """Test that last_ok_timestamp is populated."""
        data = {"state": "IDLE"}

        state = parse_prusa_connect_state(data)

        self.assertIsNotNone(state.last_ok_timestamp)
        self.assertIsInstance(state.last_ok_timestamp, datetime)


if __name__ == "__main__":
    unittest.main()
