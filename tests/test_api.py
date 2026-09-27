"""Integration tests for HTTP server, Router, and API endpoints."""

import json
import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "image")))

from dashboard.collector import ActivityTracker, NUTDataCache
from dashboard.config import ConfigManager
from dashboard.constants import STATIC_DIR
from dashboard.router import Router
from dashboard.security import SessionManager
from dashboard.server import DashboardHandler


class TestAPI(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp_dir = tempfile.TemporaryDirectory()
        cls.config_file = os.path.join(cls.tmp_dir.name, "config.json")
        cls.key_file = os.path.join(cls.tmp_dir.name, ".secret_key")

        # Initial config without password
        cls.config = ConfigManager(filepath=cls.config_file, key_file=cls.key_file)
        cls.cache = NUTDataCache()
        cls.cache.update(
            status="online",
            watts=120,
            load=15,
            battery=100,
            voltage=230.0,
            ups_status="Rete elettrica",
            ups_model="APC Back-UPS",
        )
        cls.tracker = ActivityTracker()
        cls.session_manager = SessionManager()
        cls.router = Router(
            config=cls.config,
            cache=cls.cache,
            tracker=cls.tracker,
            session_manager=cls.session_manager,
            static_dir=STATIC_DIR,
        )

        class CustomHandler(DashboardHandler):
            router = cls.router

        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), CustomHandler)
        cls.port = cls.httpd.server_address[1]
        cls.base_url = f"http://127.0.0.1:{cls.port}"

        cls.server_thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.tmp_dir.cleanup()

    def test_health_and_version_endpoints(self):
        with urllib.request.urlopen(f"{self.base_url}/api/health") as res:
            self.assertEqual(res.status, 200)
            data = json.loads(res.read().decode())
            self.assertEqual(data["status"], "ok")

        with urllib.request.urlopen(f"{self.base_url}/api/version") as res:
            self.assertEqual(res.status, 200)
            data = json.loads(res.read().decode())
            self.assertIn("version", data)

    def test_locales_endpoint(self):
        with urllib.request.urlopen(f"{self.base_url}/api/locales") as res:
            self.assertEqual(res.status, 200)
            data = json.loads(res.read().decode())
            self.assertIn("locales", data)
            self.assertIn("default", data)

    def test_static_files(self):
        # Index.html
        with urllib.request.urlopen(f"{self.base_url}/") as res:
            self.assertEqual(res.status, 200)
            self.assertIn(b"<!DOCTYPE html>", res.read())

        # Manifest.json
        with urllib.request.urlopen(f"{self.base_url}/manifest.json") as res:
            self.assertEqual(res.status, 200)
            self.assertIn("application/manifest+json", res.headers.get("Content-Type", ""))

    def test_stats_open_access(self):
        with urllib.request.urlopen(f"{self.base_url}/api/stats") as res:
            self.assertEqual(res.status, 200)
            data = json.loads(res.read().decode())
            self.assertEqual(data["status"], "online")
            self.assertEqual(data["watts"], 120)
            self.assertFalse(data["auth_required"])

    def test_auth_flow(self):
        # Set a dashboard password
        from dashboard.security import hash_password
        self.config.update({"dashboard_password_hash": hash_password("secretpass123")})
        self.assertTrue(self.config.is_auth_required())

        # /api/stats without auth should return 401
        try:
            urllib.request.urlopen(f"{self.base_url}/api/stats")
            self.fail("Expected 401 Unauthorized")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 401)

        # Login with wrong password
        login_url = f"{self.base_url}/api/login"
        bad_req = urllib.request.Request(
            login_url,
            data=json.dumps({"password": "wrong"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            urllib.request.urlopen(bad_req)
            self.fail("Expected 401 Unauthorized")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 401)

        # Login with correct password
        good_req = urllib.request.Request(
            login_url,
            data=json.dumps({"password": "secretpass123"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(good_req) as res:
            self.assertEqual(res.status, 200)
            cookie = res.headers.get("Set-Cookie")
            self.assertIsNotNone(cookie)
            self.assertIn("ups_dashboard_session=", cookie)

        # Extract session cookie value
        cookie_val = cookie.split(";")[0]

        # Access /api/stats with cookie
        auth_req = urllib.request.Request(
            f"{self.base_url}/api/stats",
            headers={"Cookie": cookie_val},
        )
        with urllib.request.urlopen(auth_req) as res:
            self.assertEqual(res.status, 200)
            data = json.loads(res.read().decode())
            self.assertEqual(data["status"], "online")

        # Update settings via POST /api/settings
        settings_req = urllib.request.Request(
            f"{self.base_url}/api/settings",
            data=json.dumps({"nut_host": "192.168.1.55", "poll_interval": 3.5}).encode("utf-8"),
            headers={"Content-Type": "application/json", "Cookie": cookie_val},
        )
        with urllib.request.urlopen(settings_req) as res:
            self.assertEqual(res.status, 200)
            resp_data = json.loads(res.read().decode())
            self.assertTrue(resp_data["success"])
            self.assertEqual(self.config.get("nut_host"), "192.168.1.55")
            self.assertEqual(self.config.get("poll_interval"), 3.5)

        # Logout
        logout_req = urllib.request.Request(
            f"{self.base_url}/api/logout",
            data=b"",
            headers={"Cookie": cookie_val},
        )
        with urllib.request.urlopen(logout_req) as res:
            self.assertEqual(res.status, 200)
            clear_cookie = res.headers.get("Set-Cookie")
            self.assertIn("Max-Age=0", clear_cookie)

        # Subsequent request with old cookie should fail (401)
        try:
            urllib.request.urlopen(auth_req)
            self.fail("Expected 401 Unauthorized after logout")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 401)

        # Clear password for next tests
        self.config.update({"dashboard_password_hash": ""})

    def test_security_headers(self):
        with urllib.request.urlopen(f"{self.base_url}/api/health") as res:
            self.assertEqual(res.headers.get("X-Content-Type-Options"), "nosniff")
            self.assertEqual(res.headers.get("X-Frame-Options"), "DENY")
            self.assertEqual(res.headers.get("Referrer-Policy"), "no-referrer")

    def test_payload_too_large(self):
        huge_data = b"x" * (1_048_576 + 10)
        req = urllib.request.Request(
            f"{self.base_url}/api/login",
            data=huge_data,
            headers={"Content-Type": "application/json"},
        )
        try:
            urllib.request.urlopen(req)
            self.fail("Expected 413 Payload Too Large")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 413)

    def test_crlf_sanitization(self):
        req = urllib.request.Request(
            f"{self.base_url}/api/settings",
            data=json.dumps({"ups_name": "ups\r\nINJECT", "nut_host": "127.0.0.1\n"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req) as res:
            self.assertEqual(res.status, 200)
            self.assertEqual(self.config.get("ups_name"), "upsINJECT")
            self.assertEqual(self.config.get("nut_host"), "127.0.0.1")


if __name__ == "__main__":
    unittest.main()
