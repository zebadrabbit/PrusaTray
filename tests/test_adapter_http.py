"""
End-to-end adapter tests against a stub HTTP server.

Covers the request wiring that the pure-parser tests cannot see: which URLs an
adapter calls, the PrusaLink /api/v1/job name lookup, the legacy 404 fallback
and the Connect printer+jobs chain.
"""

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer

from tray_prusa.adapters import PrusaConnectAdapter, PrusaLinkAdapter
from tray_prusa.models import AppConfig, PrinterStatus

# Route -> (status, body). Set per test; the handler just serves it.
ROUTES = {}
REQUESTS = []


class StubHandler(BaseHTTPRequestHandler):
    """Serves ROUTES and records what was asked for."""

    def do_GET(self):
        REQUESTS.append((self.path, dict(self.headers)))
        status, body = ROUTES.get(self.path, (404, {"message": "Not Found"}))
        payload = b"" if body is None else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass  # keep test output clean


class AdapterHttpTestCase(unittest.TestCase):
    """Shared stub server + Qt event loop plumbing."""

    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])
        cls.server = HTTPServer(("127.0.0.1", 0), StubHandler)
        cls.base_url = "http://127.0.0.1:{}".format(cls.server.server_address[1])
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        ROUTES.clear()
        REQUESTS.clear()
        # Adapters own their QNetworkAccessManager; letting one be garbage
        # collected while Qt still has deferred deletions queued on it crashes
        # the interpreter, so hold them until the event queue has drained.
        self._adapters = []

    def tearDown(self):
        for _ in range(3):
            QCoreApplication.processEvents()
        self._adapters.clear()

    def keep(self, adapter):
        """Hold a reference to an adapter for the rest of the test."""
        self._adapters.append(adapter)
        return adapter

    def fetch(self, adapter, timeout_ms=5000):
        """Run one fetch_state_async() to completion and return the result."""
        result = {}
        loop = QEventLoop()

        def on_state(state):
            result.setdefault("state", state)
            loop.quit()

        def on_error(error):
            result.setdefault("error", error)
            loop.quit()

        # An owned timer, not QTimer.singleShot: a pending singleShot outlives
        # this loop object and firing loop.quit() on the freed C++ QEventLoop
        # crashes the interpreter.
        timeout = QTimer()
        timeout.setSingleShot(True)
        timeout.timeout.connect(loop.quit)

        adapter.state_fetched.connect(on_state)
        adapter.state_error.connect(on_error)
        try:
            timeout.start(timeout_ms)
            adapter.fetch_state_async()
            loop.exec()
        finally:
            timeout.stop()
            adapter.state_fetched.disconnect(on_state)
            adapter.state_error.disconnect(on_error)

        self.assertTrue(result, "adapter emitted nothing within the timeout")
        # In the app the event loop keeps running after a state is emitted, so
        # give follow-up requests (the /api/v1/job name lookup) their turn.
        self.settle()
        return result

    def settle(self, ms=200):
        """Run the event loop briefly so deferred requests complete."""
        loop = QEventLoop()
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        timer.start(ms)
        loop.exec()
        timer.stop()

    def paths(self):
        """Paths requested so far, in order."""
        return [path for path, _ in REQUESTS]


class TestPrusaLinkAdapter(AdapterHttpTestCase):
    """PrusaLink v1 wiring."""

    V1_STATUS = {
        "printer": {"state": "PRINTING", "temp_nozzle": 214.9, "temp_bed": 59.5},
        "job": {"id": 420, "progress": 42.5, "time_remaining": 1847},
    }
    V1_JOB = {
        "id": 420,
        "state": "PRINTING",
        "file": {"name": "BENCHY~1.BGC", "display_name": "benchy.bgcode"},
    }

    def adapter(self):
        return self.keep(
            PrusaLinkAdapter(self.base_url, AppConfig(backend="prusalink"))
        )

    def test_v1_status_and_job_name_lookup(self):
        ROUTES["/api/v1/status"] = (200, self.V1_STATUS)
        ROUTES["/api/v1/job"] = (200, self.V1_JOB)
        adapter = self.adapter()

        state = self.fetch(adapter)["state"]
        self.assertEqual(state.status, PrinterStatus.PRINTING)
        self.assertAlmostEqual(state.progress, 0.425, places=3)
        self.assertEqual(state.eta_seconds, 1847)
        self.assertIn("/api/v1/status", self.paths())

        # The name arrives on the job request and shows from the next poll on.
        self.assertIn("/api/v1/job", self.paths())
        self.assertEqual(self.fetch(adapter)["state"].job_name, "benchy.bgcode")

    def test_job_name_fetched_once_per_job(self):
        ROUTES["/api/v1/status"] = (200, self.V1_STATUS)
        ROUTES["/api/v1/job"] = (200, self.V1_JOB)
        adapter = self.adapter()

        for _ in range(3):
            self.fetch(adapter)

        self.assertEqual(self.paths().count("/api/v1/job"), 1)

    def test_job_name_refetched_when_job_changes(self):
        ROUTES["/api/v1/status"] = (200, self.V1_STATUS)
        ROUTES["/api/v1/job"] = (200, self.V1_JOB)
        adapter = self.adapter()
        self.fetch(adapter)

        ROUTES["/api/v1/status"] = (
            200,
            {"printer": {"state": "PRINTING"}, "job": {"id": 421, "progress": 1.0}},
        )
        ROUTES["/api/v1/job"] = (
            200,
            {"id": 421, "file": {"display_name": "second.bgcode"}},
        )
        self.fetch(adapter)

        self.assertEqual(self.paths().count("/api/v1/job"), 2)
        self.assertEqual(self.fetch(adapter)["state"].job_name, "second.bgcode")

    def test_idle_needs_no_job_lookup(self):
        ROUTES["/api/v1/status"] = (200, {"printer": {"state": "IDLE"}})
        adapter = self.adapter()

        state = self.fetch(adapter)["state"]
        self.assertEqual(state.status, PrinterStatus.IDLE)
        self.assertIsNone(state.job_name)
        # No job id, so no point asking for a name.
        self.assertNotIn("/api/v1/job", self.paths())

    def test_attention_message_is_surfaced(self):
        ROUTES["/api/v1/status"] = (
            200,
            {
                "printer": {
                    "state": "ATTENTION",
                    "status_printer": {"ok": False, "message": "Filament runout"},
                }
            },
        )

        state = self.fetch(self.adapter())["state"]
        self.assertEqual(state.status, PrinterStatus.ATTENTION)
        self.assertEqual(state.message, "Filament runout")

    def test_falls_back_to_legacy_api_job_on_404(self):
        ROUTES["/api/job"] = (
            200,
            {
                "state": "Printing",
                "job": {"file": {"name": "old.gcode"}},
                "progress": {"completion": 67.5, "printTimeLeft": 1170},
                "temperature": {"tool0": {"actual": 215.3}, "bed": {"actual": 59.8}},
            },
        )
        adapter = self.adapter()

        state = self.fetch(adapter)["state"]
        self.assertEqual(state.status, PrinterStatus.PRINTING)
        self.assertEqual(state.job_name, "old.gcode")
        self.assertEqual(state.eta_seconds, 1170)
        self.assertEqual(self.paths(), ["/api/v1/status", "/api/job"])

        # Sticks with legacy afterwards instead of re-probing v1 every poll.
        self.fetch(adapter)
        self.assertEqual(self.paths().count("/api/v1/status"), 1)


class TestPrusaConnectAdapter(AdapterHttpTestCase):
    """Connect mobile API wiring."""

    UUID = "0f9d7c2a-3b41-4f6e-9c2d-8a1b5e7f4d33"
    PRINTER = {
        "uuid": UUID,
        "state": "PRINTING",
        "telemetry": {
            "temperatureNozzleCurrent": 214.9,
            "temperatureHeatbedCurrent": 59.5,
        },
    }
    JOBS = [{"id": "j1", "state": "PRINTING", "progress": 42.5, "fileName": "b.bgcode"}]

    def printer_path(self):
        return "/api/v1/printers/{}".format(self.UUID)

    def jobs_path(self):
        return "/api/v1/jobs?printer={}&itemsPerPage=1".format(self.UUID)

    def config(self, token="jwt-token-value"):
        return AppConfig(
            backend="prusaconnect", bearer_token=token, printer_uuid=self.UUID
        )

    def test_printer_and_jobs_are_combined(self):
        ROUTES[self.printer_path()] = (200, self.PRINTER)
        ROUTES[self.jobs_path()] = (200, self.JOBS)
        adapter = self.keep(PrusaConnectAdapter(self.base_url, self.config()))

        state = self.fetch(adapter)["state"]
        self.assertEqual(state.status, PrinterStatus.PRINTING)
        self.assertAlmostEqual(state.progress, 0.425, places=3)
        self.assertEqual(state.job_name, "b.bgcode")
        self.assertEqual(state.nozzle_temp, 214.9)
        self.assertEqual(self.paths(), [self.printer_path(), self.jobs_path()])

    def test_bearer_prefix_added_to_bare_token(self):
        ROUTES[self.printer_path()] = (200, self.PRINTER)
        adapter = self.keep(
            PrusaConnectAdapter(self.base_url, self.config("jwt-token-value"))
        )

        self.fetch(adapter)
        self.assertEqual(REQUESTS[0][1]["Authorization"], "Bearer jwt-token-value")

    def test_token_with_scheme_is_sent_verbatim(self):
        ROUTES[self.printer_path()] = (200, self.PRINTER)
        adapter = self.keep(
            PrusaConnectAdapter(self.base_url, self.config("Bearer already-set"))
        )

        self.fetch(adapter)
        self.assertEqual(REQUESTS[0][1]["Authorization"], "Bearer already-set")

    def test_jsonld_job_collection_is_unwrapped(self):
        ROUTES[self.printer_path()] = (200, self.PRINTER)
        ROUTES[self.jobs_path()] = (200, {"hydra:member": self.JOBS})
        adapter = self.keep(PrusaConnectAdapter(self.base_url, self.config()))

        self.assertEqual(self.fetch(adapter)["state"].job_name, "b.bgcode")

    def test_state_still_reported_when_jobs_request_fails(self):
        ROUTES[self.printer_path()] = (200, self.PRINTER)
        # jobs route missing -> 404, but the printer state is still worth showing
        adapter = self.keep(PrusaConnectAdapter(self.base_url, self.config()))

        state = self.fetch(adapter)["state"]
        self.assertEqual(state.status, PrinterStatus.PRINTING)
        self.assertEqual(state.nozzle_temp, 214.9)
        self.assertIsNone(state.progress)

    def test_401_reports_auth_error(self):
        ROUTES[self.printer_path()] = (401, {"message": "Unauthorized"})
        adapter = self.keep(PrusaConnectAdapter(self.base_url, self.config()))

        self.assertIn("Auth failed", self.fetch(adapter)["error"])

    def test_missing_config_is_rejected(self):
        with self.assertRaises(ValueError):
            PrusaConnectAdapter(self.base_url, AppConfig(backend="prusaconnect"))
        with self.assertRaises(ValueError):
            PrusaConnectAdapter(
                self.base_url, AppConfig(backend="prusaconnect", bearer_token="t")
            )


if __name__ == "__main__":
    unittest.main()
