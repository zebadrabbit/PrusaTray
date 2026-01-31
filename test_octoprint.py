"""Unit tests for OctoPrint parser."""

import unittest
from datetime import datetime
from tray_prusa.adapters import parse_octoprint_state
from tray_prusa.models import PrinterStatus


class TestOctoPrintParser(unittest.TestCase):
    """Test OctoPrint API response parsing."""
    
    def test_printing_state(self):
        """Test OctoPrint /api/job response while printing."""
        data = {
            "state": "Printing",
            "job": {
                "file": {
                    "name": "test_print.gcode",
                    "size": 1024000
                },
                "estimatedPrintTime": 3600
            },
            "progress": {
                "completion": 42.5,
                "printTime": 1200,
                "printTimeLeft": 1800
            }
        }
        
        state = parse_octoprint_state(data)
        
        self.assertEqual(state.status, PrinterStatus.PRINTING)
        self.assertAlmostEqual(state.progress, 0.425, places=3)
        self.assertEqual(state.eta_seconds, 1800)
        self.assertEqual(state.job_name, "test_print.gcode")
    
    def test_state_as_dict(self):
        """Test OctoPrint state as dict with text field."""
        data = {
            "state": {
                "text": "Printing",
                "flags": {
                    "operational": True,
                    "printing": True,
                    "paused": False
                }
            },
            "job": {
                "file": {"name": "model.gcode"}
            },
            "progress": {
                "completion": 75.0,
                "printTimeLeft": 600
            }
        }
        
        state = parse_octoprint_state(data)
        
        self.assertEqual(state.status, PrinterStatus.PRINTING)
        self.assertAlmostEqual(state.progress, 0.75, places=2)
        self.assertEqual(state.eta_seconds, 600)
    
    def test_operational_idle_state(self):
        """Test OctoPrint operational/idle state."""
        data = {
            "state": "Operational",
            "job": None,
            "progress": {
                "completion": None,
                "printTime": None,
                "printTimeLeft": None
            }
        }
        
        state = parse_octoprint_state(data)
        
        self.assertEqual(state.status, PrinterStatus.IDLE)
        self.assertIsNone(state.progress)
        self.assertIsNone(state.eta_seconds)
        self.assertIsNone(state.job_name)
    
    def test_paused_state(self):
        """Test OctoPrint paused state."""
        data = {
            "state": "Paused",
            "job": {
                "file": {"name": "paused_print.gcode"}
            },
            "progress": {
                "completion": 60.0,
                "printTime": 1800,
                "printTimeLeft": 1200
            }
        }
        
        state = parse_octoprint_state(data)
        
        self.assertEqual(state.status, PrinterStatus.PAUSED)
        self.assertAlmostEqual(state.progress, 0.60, places=2)
        self.assertEqual(state.eta_seconds, 1200)
    
    def test_offline_state(self):
        """Test OctoPrint offline state."""
        data = {
            "state": "Offline",
            "job": None,
            "progress": None
        }
        
        state = parse_octoprint_state(data)
        
        self.assertEqual(state.status, PrinterStatus.OFFLINE)
        self.assertIsNone(state.progress)
    
    def test_error_state(self):
        """Test OctoPrint error state."""
        data = {
            "state": "Error",
            "job": None,
            "progress": None
        }
        
        state = parse_octoprint_state(data)
        
        self.assertEqual(state.status, PrinterStatus.ERROR)
    
    def test_with_temperature_data(self):
        """Test OctoPrint response with temperature data."""
        data = {
            "state": "Printing",
            "job": {
                "file": {"name": "temp_test.gcode"}
            },
            "progress": {
                "completion": 50.0,
                "printTimeLeft": 900
            },
            "temperature": {
                "tool0": {
                    "actual": 210.5,
                    "target": 210.0
                },
                "bed": {
                    "actual": 60.2,
                    "target": 60.0
                }
            }
        }
        
        state = parse_octoprint_state(data)
        
        self.assertEqual(state.status, PrinterStatus.PRINTING)
        self.assertEqual(state.nozzle_temp, 210.5)
        self.assertEqual(state.bed_temp, 60.2)
    
    def test_completion_100_percent(self):
        """Test 100% completion."""
        data = {
            "state": "Operational",
            "job": {
                "file": {"name": "finished.gcode"}
            },
            "progress": {
                "completion": 100.0,
                "printTime": 3600,
                "printTimeLeft": 0
            }
        }
        
        state = parse_octoprint_state(data)
        
        self.assertEqual(state.status, PrinterStatus.IDLE)
        self.assertAlmostEqual(state.progress, 1.0, places=2)
        self.assertEqual(state.eta_seconds, 0)
    
    def test_missing_progress_data(self):
        """Test handling of missing progress data."""
        data = {
            "state": "Printing",
            "job": {
                "file": {"name": "no_progress.gcode"}
            }
            # No progress field
        }
        
        state = parse_octoprint_state(data)
        
        self.assertEqual(state.status, PrinterStatus.PRINTING)
        self.assertIsNone(state.progress)
        self.assertIsNone(state.eta_seconds)
        self.assertEqual(state.job_name, "no_progress.gcode")
    
    def test_missing_job_data(self):
        """Test handling of missing job data."""
        data = {
            "state": "Operational",
            "progress": {
                "completion": None
            }
            # No job field
        }
        
        state = parse_octoprint_state(data)
        
        self.assertEqual(state.status, PrinterStatus.IDLE)
        self.assertIsNone(state.job_name)
    
    def test_empty_data_returns_unknown(self):
        """Test that empty data returns unknown state."""
        data = {}
        
        state = parse_octoprint_state(data)
        
        # Empty data with no state field should return UNKNOWN
        self.assertEqual(state.status, PrinterStatus.UNKNOWN)
    
    def test_invalid_state_type(self):
        """Test handling of invalid state type."""
        data = {
            "state": None,  # Invalid type
            "job": {
                "file": {"name": "test.gcode"}
            },
            "progress": {
                "completion": 25.0
            }
        }
        
        state = parse_octoprint_state(data)
        
        # Should default to UNKNOWN
        self.assertEqual(state.status, PrinterStatus.UNKNOWN)
    
    def test_malformed_file_info(self):
        """Test handling of malformed file info."""
        data = {
            "state": "Printing",
            "job": {
                "file": "not_a_dict"  # Should be dict
            },
            "progress": {
                "completion": 50.0,
                "printTimeLeft": 600
            }
        }
        
        state = parse_octoprint_state(data)
        
        self.assertEqual(state.status, PrinterStatus.PRINTING)
        self.assertIsNone(state.job_name)  # Gracefully handle bad data
        self.assertAlmostEqual(state.progress, 0.5, places=1)


if __name__ == '__main__':
    unittest.main()
