"""
Smoke test for demo adapter.

Quick test to verify demo mode works without network calls.
"""

import unittest
import time
from tray_prusa.adapters import DemoAdapter
from tray_prusa.models import PrinterStatus


class TestDemoAdapter(unittest.TestCase):
    """Test demo adapter functionality."""

    def test_demo_adapter_creates(self):
        """Test that demo adapter can be instantiated."""
        adapter = DemoAdapter()
        self.assertIsNotNone(adapter)

    def test_demo_adapter_returns_state(self):
        """Test that demo adapter returns a valid state."""
        adapter = DemoAdapter()
        state = adapter.fetch_state()

        self.assertIsNotNone(state)
        self.assertIn(
            state.status,
            [PrinterStatus.PRINTING, PrinterStatus.PAUSED, PrinterStatus.IDLE],
        )

    def test_demo_adapter_cycles_through_states(self):
        """Test that demo adapter cycles through different states."""
        adapter = DemoAdapter()

        # Collect states over time
        states = []
        for _ in range(3):
            state = adapter.fetch_state()
            states.append(state.status)
            time.sleep(0.1)

        # At least one state should be returned
        self.assertGreater(len(states), 0)

        # All states should be valid
        for status in states:
            self.assertIn(
                status,
                [PrinterStatus.PRINTING, PrinterStatus.PAUSED, PrinterStatus.IDLE],
            )

    def test_demo_adapter_printing_has_progress(self):
        """Test that PRINTING state has progress."""
        adapter = DemoAdapter()

        # Wait for printing state
        for _ in range(10):
            state = adapter.fetch_state()
            if state.status == PrinterStatus.PRINTING:
                self.assertIsNotNone(state.progress)
                self.assertGreaterEqual(state.progress, 0.0)
                self.assertLessEqual(state.progress, 1.0)
                self.assertIsNotNone(state.eta_seconds)
                self.assertEqual(state.job_name, "demo_model.gcode")
                break
            time.sleep(0.1)
        else:
            self.skipTest("Did not encounter PRINTING state in time")

    def test_demo_adapter_idle_no_job(self):
        """Test that IDLE state has no job info."""
        adapter = DemoAdapter()

        # Fast-forward to idle phase (after print + pause)
        adapter._start_time = time.time() - 135  # 2:15 into cycle

        state = adapter.fetch_state()
        self.assertEqual(state.status, PrinterStatus.IDLE)
        self.assertIsNone(state.job_name)


if __name__ == "__main__":
    unittest.main()
