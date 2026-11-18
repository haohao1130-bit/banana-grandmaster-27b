"""Safety checks for the independent 27B restart supervisor; no GPU needed."""
import io
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from tools import supervise_27b
from banana_mv import server


class SupervisorTests(unittest.TestCase):
    def test_accepts_only_fresh_own_instance(self):
        fresh = {"version": 1, "instance": "ours", "issued_at": time.time()}
        self.assertTrue(supervise_27b.valid_request(fresh, "ours"))
        self.assertFalse(supervise_27b.valid_request(fresh, "foreign"))
        self.assertFalse(supervise_27b.valid_request(
            dict(fresh, issued_at=time.time() - 120), "ours"))
        self.assertFalse(supervise_27b.valid_request(
            dict(fresh, version=2), "ours"))
        self.assertFalse(supervise_27b.valid_request(None, "ours"))

    def test_health_must_be_own_process_and_standalone(self):
        def response(payload):
            return io.BytesIO(json.dumps(payload).encode("utf-8"))
        with patch.object(supervise_27b.request, "urlopen",
                          return_value=response({"standalone": True, "instance": "ours", "pid": 1234})):
            self.assertEqual(supervise_27b.current_instance(1234), "ours")
            self.assertIsNone(supervise_27b.current_instance(4567))
        with patch.object(supervise_27b.request, "urlopen",
                          return_value=response({"standalone": False, "instance": "foreign", "pid": 1234})):
            self.assertIsNone(supervise_27b.current_instance(1234))


class RequestTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.dest = Path(self.folder.name) / "restart-request.json"
        self.req = patch.object(server, "RESTART_REQUEST", self.dest)
        self.req.start()
        self.addCleanup(self.req.stop)
        self.env = patch.dict(os.environ, {"BANANA_27B_STANDALONE": "1"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.handler = type("Handler", (), {"headers": {
            "Origin": "https://desktop.example.ts.net",
            "Host": "127.0.0.1:8193",
            "X-Forwarded-Host": "desktop.example.ts.net",
            "Content-Type": "application/json",
            "Sec-Fetch-Site": "same-origin",
            "X-Banana-Control": "27b-restart",
        }})()

    def test_accepts_idle_browser_request_and_releases_own_llama(self):
        with patch.object(server, "restart_capability", return_value={
                    "available": True, "busy": False, "reason": ""}), \
             patch.object(server.backend, "comfy", return_value={}), \
             patch.object(server.backend, "cancel_27b") as stop:
            result = server.request_desktop_restart(
                self.handler, {"confirm": "restart-27b"})
        self.assertTrue(result["restarting"])
        self.assertEqual(json.loads(self.dest.read_text())["instance"],
                         server.SERVER_INSTANCE)
        stop.assert_called_once_with()

    def test_rejects_busy_and_cross_site_restarts(self):
        with patch.object(server, "restart_capability", return_value={
                    "available": True, "busy": True, "reason": "busy"}):
            with self.assertRaises(ValueError):
                server.request_desktop_restart(
                    self.handler, {"confirm": "restart-27b"})
        self.assertFalse(self.dest.exists())
        self.handler.headers["Origin"] = "https://untrusted.example"
        with self.assertRaises(ValueError):
            server.request_desktop_restart(
                self.handler, {"confirm": "restart-27b"})
        self.assertFalse(self.dest.exists())

    def test_rejects_active_h3_queue(self):
        with patch.object(server, "restart_capability", return_value={
                    "available": True, "busy": False, "reason": ""}), \
             patch.object(server.backend, "comfy", return_value={
                 "queue_pending": ["queued"]}), \
             patch.object(server.backend, "cancel_27b") as stop:
            with self.assertRaises(ValueError):
                server.request_desktop_restart(
                    self.handler, {"confirm": "restart-27b"})
            stop.assert_not_called()
        self.assertFalse(self.dest.exists())


if __name__ == "__main__":
    unittest.main()
