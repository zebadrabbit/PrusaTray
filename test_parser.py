"""Unit tests for parsing functions (example)."""

import unittest
from tray_prusa.models import PrinterStatus
from tray_prusa.adapters import normalize_status, parse_demo_state, clamp


class TestNormalizeStatus(unittest.TestCase):
    """Test status normalization."""
    
    def test_idle_variations(self):
        """Test various idle status strings."""
        for status in ["idle", "IDLE", "ready", "operational"]:
            self.assertEqual(normalize_status(status), PrinterStatus.IDLE)
    
    def test_printing_variations(self):
        """Test various printing status strings."""
        for status in ["printing", "PRINTING", "busy", "working"]:
            self.assertEqual(normalize_status(status), PrinterStatus.PRINTING)
    
    def test_paused(self):
        """Test paused status."""
        self.assertEqual(normalize_status("paused"), PrinterStatus.PAUSED)
        self.assertEqual(normalize_status("PAUSING"), PrinterStatus.PAUSED)
    
    def test_error(self):
        """Test error status."""
        self.assertEqual(normalize_status("error"), PrinterStatus.ERROR)
        self.assertEqual(normalize_status("FAILED"), PrinterStatus.ERROR)
    
    def test_unknown(self):
        """Test unknown status."""
        self.assertEqual(normalize_status("weird_state"), PrinterStatus.UNKNOWN)
        self.assertEqual(normalize_status(None), PrinterStatus.UNKNOWN)


class TestClamp(unittest.TestCase):
    """Test clamping function."""
    
    def test_within_range(self):
        """Test value within range."""
        self.assertEqual(clamp(0.5), 0.5)
    
    def test_below_min(self):
        """Test value below minimum."""
        self.assertEqual(clamp(-0.5), 0.0)
    
    def test_above_max(self):
        """Test value above maximum."""
        self.assertEqual(clamp(1.5), 1.0)
    
    def test_none(self):
        """Test None handling."""
        self.assertIsNone(clamp(None))


class TestDemoStateParser(unittest.TestCase):
    """Test demo state creation."""
    
    def test_printing_state(self):
        """Test printing state creation."""
        state = parse_demo_state(
            status=PrinterStatus.PRINTING,
            progress=0.5,
            eta_seconds=1800,
            job_name="test.gcode"
        )
        self.assertEqual(state.status, PrinterStatus.PRINTING)
        self.assertEqual(state.progress, 0.5)
        self.assertEqual(state.eta_seconds, 1800)
        self.assertEqual(state.job_name, "test.gcode")
        self.assertEqual(state.nozzle_temp, 215.0)
        self.assertEqual(state.bed_temp, 60.0)
        self.assertIsNotNone(state.last_ok_timestamp)
    
    def test_idle_state(self):
        """Test idle state has no temps."""
        state = parse_demo_state(status=PrinterStatus.IDLE)
        self.assertEqual(state.status, PrinterStatus.IDLE)
        self.assertIsNone(state.nozzle_temp)
        self.assertIsNone(state.bed_temp)
    
    def test_progress_clamping(self):
        """Test progress is clamped to 0-1."""
        state = parse_demo_state(PrinterStatus.PRINTING, progress=1.5)
        self.assertEqual(state.progress, 1.0)
        
        state = parse_demo_state(PrinterStatus.PRINTING, progress=-0.5)
        self.assertEqual(state.progress, 0.0)


if __name__ == "__main__":
    unittest.main()
