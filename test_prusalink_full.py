"""Unit tests for PrusaLink parser."""

import unittest
from datetime import datetime
from tray_prusa.adapters import parse_prusalink_state
from tray_prusa.models import PrinterStatus


class TestPrusaLinkParser(unittest.TestCase):
    """Test PrusaLink API response parsing."""
    
    def test_v1_printing_state(self):
        """Test v1 API format with printing state."""
        data = {
            "printer": {
                "state": "PRINTING",
                "temp_nozzle": 215.0,
                "temp_bed": 60.0
            },
            "job": {
                "progress": 45.5,
                "time_remaining": 1800,
                "file": {
                    "name": "test_model.gcode"
                }
            }
        }
        
        state = parse_prusalink_state(data)
        
        self.assertEqual(state.status, PrinterStatus.PRINTING)
        self.assertAlmostEqual(state.progress, 0.455, places=3)
        self.assertEqual(state.eta_seconds, 1800)
        self.assertEqual(state.job_name, "test_model.gcode")
        self.assertEqual(state.nozzle_temp, 215.0)
        self.assertEqual(state.bed_temp, 60.0)
    
    def test_v1_idle_state(self):
        """Test v1 API format with idle state (no job)."""
        data = {
            "printer": {
                "state": "IDLE",
                "temp_nozzle": 25.0,
                "temp_bed": 22.0
            },
            "job": None
        }
        
        state = parse_prusalink_state(data)
        
        self.assertEqual(state.status, PrinterStatus.IDLE)
        self.assertIsNone(state.progress)
        self.assertIsNone(state.eta_seconds)
        self.assertIsNone(state.job_name)
        self.assertEqual(state.nozzle_temp, 25.0)
    
    def test_legacy_printing_completion_decimal(self):
        """Test legacy API with completion as 0-1 decimal."""
        data = {
            "state": "Printing",
            "job": {
                "file": {
                    "name": "benchy.gcode"
                }
            },
            "progress": {
                "completion": 0.88,
                "printTimeLeft": 960
            },
            "temperature": {
                "tool0": {"actual": 210},
                "bed": {"actual": 55}
            }
        }
        
        state = parse_prusalink_state(data)
        
        self.assertEqual(state.status, PrinterStatus.PRINTING)
        self.assertAlmostEqual(state.progress, 0.88, places=2)
        self.assertEqual(state.eta_seconds, 960)
        self.assertEqual(state.job_name, "benchy.gcode")
        self.assertEqual(state.nozzle_temp, 210)
        self.assertEqual(state.bed_temp, 55)
    
    def test_legacy_printing_completion_percent(self):
        """Test legacy API with completion as 0-100 percentage."""
        data = {
            "state": "Printing",
            "job": {
                "file": {
                    "name": "cube.gcode"
                }
            },
            "progress": {
                "completion": 88,
                "printTimeLeft": 720
            },
            "temperature": {
                "tool0": {"actual": 200},
                "bed": {"actual": 50}
            }
        }
        
        state = parse_prusalink_state(data)
        
        self.assertEqual(state.status, PrinterStatus.PRINTING)
        self.assertAlmostEqual(state.progress, 0.88, places=2)
        self.assertEqual(state.eta_seconds, 720)
    
    def test_legacy_operational_null_job(self):
        """Test legacy API with Operational state and null job (idle)."""
        data = {
            "state": "Operational",
            "job": None,
            "progress": None,
            "temperature": {
                "tool0": {"actual": 28},
                "bed": {"actual": 25}
            }
        }
        
        state = parse_prusalink_state(data)
        
        self.assertEqual(state.status, PrinterStatus.IDLE)
        self.assertIsNone(state.progress)
        self.assertIsNone(state.eta_seconds)
        self.assertIsNone(state.job_name)
    
    def test_v1_paused_state(self):
        """Test v1 API with paused state."""
        data = {
            "printer": {
                "state": "PAUSED",
                "temp_nozzle": 215.0,
                "temp_bed": 60.0
            },
            "job": {
                "progress": 60.0,
                "time_remaining": 1200,
                "file": {
                    "name": "paused_print.gcode"
                }
            }
        }
        
        state = parse_prusalink_state(data)
        
        self.assertEqual(state.status, PrinterStatus.PAUSED)
        self.assertAlmostEqual(state.progress, 0.60, places=2)
        self.assertEqual(state.eta_seconds, 1200)
    
    def test_v1_error_state(self):
        """Test v1 API with error state."""
        data = {
            "printer": {
                "state": "ERROR",
                "temp_nozzle": 0.0,
                "temp_bed": 0.0
            },
            "job": None
        }
        
        state = parse_prusalink_state(data)
        
        self.assertEqual(state.status, PrinterStatus.ERROR)
        self.assertIsNone(state.progress)
    
    def test_missing_fields_graceful(self):
        """Test that missing fields don't crash parser."""
        data = {
            "printer": {
                "state": "PRINTING"
                # Missing temps
            },
            "job": {
                "progress": 50
                # Missing time_remaining and file
            }
        }
        
        state = parse_prusalink_state(data)
        
        self.assertEqual(state.status, PrinterStatus.PRINTING)
        self.assertAlmostEqual(state.progress, 0.5, places=1)
        self.assertIsNone(state.nozzle_temp)
        self.assertIsNone(state.bed_temp)
        self.assertIsNone(state.eta_seconds)
        self.assertIsNone(state.job_name)
    
    def test_legacy_missing_temperature(self):
        """Test legacy format with missing temperature data."""
        data = {
            "state": "Printing",
            "job": {
                "file": {"name": "test.gcode"}
            },
            "progress": {
                "completion": 0.5,
                "printTimeLeft": 600
            }
            # No temperature field
        }
        
        state = parse_prusalink_state(data)
        
        self.assertEqual(state.status, PrinterStatus.PRINTING)
        self.assertIsNone(state.nozzle_temp)
        self.assertIsNone(state.bed_temp)
    
    def test_empty_data_returns_unknown(self):
        """Test that completely empty data returns unknown state."""
        data = {}
        
        state = parse_prusalink_state(data)
        
        # Empty data should return UNKNOWN status (no printer/state field)
        self.assertEqual(state.status, PrinterStatus.UNKNOWN)
    
    def test_v1_completion_100_percent(self):
        """Test v1 format with 100% completion."""
        data = {
            "printer": {
                "state": "PRINTING",
                "temp_nozzle": 215.0,
                "temp_bed": 60.0
            },
            "job": {
                "progress": 100.0,
                "time_remaining": 0,
                "file": {
                    "name": "finished.gcode"
                }
            }
        }
        
        state = parse_prusalink_state(data)
        
        self.assertEqual(state.status, PrinterStatus.PRINTING)
        self.assertAlmostEqual(state.progress, 1.0, places=2)
        self.assertEqual(state.eta_seconds, 0)
    
    def test_legacy_completion_100_decimal(self):
        """Test legacy format with 1.0 completion (100%)."""
        data = {
            "state": "Operational",
            "job": {
                "file": {"name": "done.gcode"}
            },
            "progress": {
                "completion": 1.0,
                "printTimeLeft": 0
            },
            "temperature": {
                "tool0": {"actual": 50},
                "bed": {"actual": 30}
            }
        }
        
        state = parse_prusalink_state(data)
        
        self.assertEqual(state.status, PrinterStatus.IDLE)
        self.assertAlmostEqual(state.progress, 1.0, places=2)


if __name__ == '__main__':
    unittest.main()
