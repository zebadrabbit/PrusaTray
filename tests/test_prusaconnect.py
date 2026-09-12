"""
Test the Prusa Connect parser.

Payload shapes follow the published Connect mobile API OpenAPI spec
(https://connect-mobile-api.prusa3d.com/api/docs). Fixture data only - no
network calls.
"""

import time
import unittest

from tray_prusa.models import PrinterStatus
from tray_prusa.adapters import parse_prusa_connect_state

PRINTER = {
    "uuid": "0f9d7c2a-3b41-4f6e-9c2d-8a1b5e7f4d33",
    "name": "MK4 Office",
    "state": "PRINTING",
    "telemetry": {
        "temperatureNozzleCurrent": 214.9,
        "temperatureNozzleTarget": 215.0,
        "temperatureHeatbedCurrent": 59.5,
        "temperatureHeatbedTarget": 60.0,
        "speed": 100,
    },
}


def job(**overrides):
    """Build a Connect job resource with sensible defaults."""
    base = {
        "id": "7f3c1a90",
        "state": "PRINTING",
        "progress": 42.5,
        "fileName": "benchy.bgcode",
        "endAt": int(time.time()) + 600,
        "estimatedPrintTime": 2829,
    }
    base.update(overrides)
    return base


class TestPrusaConnectParser(unittest.TestCase):
    """parse_prusa_connect_state() against the documented resource shapes."""

    def test_printing(self):
        state = parse_prusa_connect_state(PRINTER, job())

        self.assertEqual(state.status, PrinterStatus.PRINTING)
        self.assertAlmostEqual(state.progress, 0.425, places=3)
        self.assertEqual(state.job_name, "benchy.bgcode")
        self.assertEqual(state.nozzle_temp, 214.9)
        self.assertEqual(state.bed_temp, 59.5)
        self.assertIsNone(state.error_message)

    def test_eta_from_end_at(self):
        """Connect gives an absolute finish time; we show a countdown."""
        state = parse_prusa_connect_state(PRINTER, job(endAt=int(time.time()) + 600))

        self.assertIsNotNone(state.eta_seconds)
        self.assertAlmostEqual(state.eta_seconds, 600, delta=5)

    def test_eta_falls_back_to_estimate(self):
        """No endAt: derive the remainder from estimatedPrintTime and progress."""
        state = parse_prusa_connect_state(
            PRINTER, job(endAt=None, estimatedPrintTime=1000, progress=40.0)
        )

        self.assertEqual(state.eta_seconds, 600)

    def test_eta_absent_when_unknown(self):
        state = parse_prusa_connect_state(
            PRINTER, job(endAt=None, estimatedPrintTime=None)
        )

        self.assertIsNone(state.eta_seconds)

    def test_finished_job_is_not_reported_as_progress(self):
        """Connect keeps listing the last job; a finished one must not show up."""
        for finished in ("FIN_OK", "FIN_ERROR", "FIN_STOPPED", "FIN_HARVESTED"):
            with self.subTest(state=finished):
                state = parse_prusa_connect_state(
                    {**PRINTER, "state": "IDLE"}, job(state=finished)
                )

                self.assertEqual(state.status, PrinterStatus.IDLE)
                self.assertIsNone(state.progress)
                self.assertIsNone(state.job_name)
                self.assertIsNone(state.eta_seconds)

    def test_paused_job_still_reports_progress(self):
        state = parse_prusa_connect_state(
            {**PRINTER, "state": "PAUSED"}, job(state="PAUSED")
        )

        self.assertEqual(state.status, PrinterStatus.PAUSED)
        self.assertAlmostEqual(state.progress, 0.425, places=3)

    def test_no_job(self):
        state = parse_prusa_connect_state({**PRINTER, "state": "IDLE"}, None)

        self.assertEqual(state.status, PrinterStatus.IDLE)
        self.assertIsNone(state.progress)
        self.assertIsNone(state.job_name)

    def test_printer_states(self):
        """Every state in the Connect Printer.state enum maps to something sane."""
        expected = {
            "IDLE": PrinterStatus.IDLE,
            "READY": PrinterStatus.IDLE,
            "FINISHED": PrinterStatus.IDLE,
            "STOPPED": PrinterStatus.IDLE,
            "BUSY": PrinterStatus.IDLE,
            "MANIPULATING": PrinterStatus.IDLE,
            "PRINTING": PrinterStatus.PRINTING,
            "PAUSED": PrinterStatus.PAUSED,
            "ATTENTION": PrinterStatus.ATTENTION,
            "ERROR": PrinterStatus.ERROR,
            "OFFLINE": PrinterStatus.OFFLINE,
            "UNKNOWN": PrinterStatus.UNKNOWN,
        }
        for raw, status in expected.items():
            with self.subTest(state=raw):
                state = parse_prusa_connect_state({**PRINTER, "state": raw}, None)
                self.assertEqual(state.status, status)

    def test_missing_telemetry(self):
        """supportsTelemetry=false printers report state only."""
        state = parse_prusa_connect_state({"uuid": "x", "state": "IDLE"}, None)

        self.assertEqual(state.status, PrinterStatus.IDLE)
        self.assertIsNone(state.nozzle_temp)
        self.assertIsNone(state.bed_temp)

    def test_empty_payload_does_not_raise(self):
        state = parse_prusa_connect_state({}, None)

        self.assertEqual(state.status, PrinterStatus.UNKNOWN)

    def test_garbage_payload_does_not_raise(self):
        state = parse_prusa_connect_state(
            {"state": "PRINTING", "telemetry": "nope"}, None
        )

        self.assertEqual(state.status, PrinterStatus.ERROR)
        self.assertIsNotNone(state.error_message)


if __name__ == "__main__":
    unittest.main()
