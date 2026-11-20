"""Integration tests for HTTP server, Router, static asset serving, and REST API endpoints."""

import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "image")))

from dashboard.collector import ActivityTracker, NUTDataCache
from dashboard.config import ConfigManager
from dashboard.constants import STATIC_DIR
from dashboard.router import Router
from dashboard.security import PasswordHasher, SessionManager
from dashboard.server import DashboardHandler, DashboardHTTPServer


class TestAPI(unittest.TestCase):
    """End-to-end tests exercising HTTP routing, authentication, validation, and static assets."""

    @classmethod
    def setUpClass(cls):
        cls.tmp_dir = tempfile.TemporaryDirectory()
        cls.config_file = os.path.join(cls.tmp_dir.name, "config.json")
        cls.key_file = os.path.join(cls.tmp_dir.name, ".secret_key")

        cls.config = ConfigManager(filepath=cls.config_file, key_file=cls.key_file)
        cls.cache = NUTDataCache()
        cls.cache.update(
            status="online",
            watts=120,
            load=15,
            battery=100,
            voltage=230.0,
            ups_status="Utility Power",
            ups_status_raw="OL",
            ups_model="Generic UPS 1000",
            battery_charge_low=30,
            battery_runtime=3405,
            battery_runtime_low=300,
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

        cls.httpd = DashboardHTTPServer(("127.0.0.1", 0), DashboardHandler, cls.router)
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
            self.assertEqual(data["default"], "en")

    def test_static_files(self):
        # index.html injects APP_VERSION and references modular CSS & ES6 entrypoint.
        with urllib.request.urlopen(f"{self.base_url}/") as res:
            self.assertEqual(res.status, 200)
            index_body = res.read().decode("utf-8")
            self.assertIn("<!DOCTYPE html>", index_body)
            self.assertNotIn("__APP_VERSION__", index_body)
            self.assertIn(f'content="{self.router.version}"', index_body)
            self.assertIn(f'/css/styles.css?v={self.router.version}', index_body)
            self.assertIn(f'/js/app.js?v={self.router.version}', index_body)

        # Modular CSS stylesheet served with correct MIME type.
        with urllib.request.urlopen(f"{self.base_url}/css/styles.css") as res:
            self.assertEqual(res.status, 200)
            self.assertIn("text/css", res.headers.get("Content-Type", ""))

        # Modular ES6 JS entrypoint served with correct MIME type.
        with urllib.request.urlopen(f"{self.base_url}/js/app.js") as res:
            self.assertEqual(res.status, 200)
            self.assertIn("application/javascript", res.headers.get("Content-Type", ""))

        # Locale JSON served with Cache-Control: no-cache and supports ?v= cache-buster.
        with urllib.request.urlopen(f"{self.base_url}/locales/en.json?v={self.router.version}") as res:
            self.assertEqual(res.status, 200)
            self.assertEqual(res.headers.get("Cache-Control"), "no-cache")
            en_locale = json.loads(res.read().decode("utf-8"))
            self.assertEqual(en_locale["tab_status"]["field_charge_low"], "Low Charge Threshold")
            self.assertEqual(en_locale["tab_status"]["field_runtime_low"], "Low Runtime Threshold")

        # Web App Manifest served with manifest MIME type.
        with urllib.request.urlopen(f"{self.base_url}/manifest.json") as res:
            self.assertEqual(res.status, 200)
            self.assertIn("application/manifest+json", res.headers.get("Content-Type", ""))

        # Service Worker dynamically injects APP_VERSION without hardcoding versions in sw.js.
        with urllib.request.urlopen(f"{self.base_url}/sw.js") as res:
            self.assertEqual(res.status, 200)
            sw_body = res.read().decode("utf-8")
            self.assertNotIn("__APP_VERSION__", sw_body)
            self.assertIn(f"ups-dashboard-v{self.router.version}", sw_body)

    def test_directory_traversal_blocked(self):
        try:
            urllib.request.urlopen(f"{self.base_url}/../app.py")
            self.fail("Expected 404 Not Found for directory traversal attempt")
        except urllib.error.HTTPError as exc:
            self.assertEqual(exc.code, 404)
            exc.close()

    def test_stats_open_access(self):
        with urllib.request.urlopen(f"{self.base_url}/api/stats") as res:
            self.assertEqual(res.status, 200)
            data = json.loads(res.read().decode())
            self.assertEqual(data["status"], "online")
            self.assertEqual(data["watts"], 120)
            self.assertEqual(data["battery_charge_low"], 30)
            self.assertEqual(data["battery_runtime"], 3405)
            self.assertEqual(data["battery_runtime_low"], 300)
            self.assertFalse(data["auth_required"])

        with urllib.request.urlopen(f"{self.base_url}/api/settings") as res:
            self.assertEqual(res.status, 200)
            settings_data = json.loads(res.read().decode())
            self.assertEqual(settings_data["battery_charge_low"], 30)
            self.assertEqual(settings_data["battery_runtime"], 3405)
            self.assertEqual(settings_data["battery_runtime_low"], 300)

    def test_auth_flow(self):
        self.config.update({"dashboard_password_hash": PasswordHasher.hash("secretpass123")})
        self.assertTrue(self.config.is_auth_required())

        # /api/stats without credentials must return 401.
        try:
            urllib.request.urlopen(f"{self.base_url}/api/stats")
            self.fail("Expected 401 Unauthorized")
        except urllib.error.HTTPError as exc:
            self.assertEqual(exc.code, 401)
            exc.close()

        # Login with wrong password must return 401.
        login_url = f"{self.base_url}/api/login"
        bad_req = urllib.request.Request(
            login_url,
            data=json.dumps({"password": "wrong"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            urllib.request.urlopen(bad_req)
            self.fail("Expected 401 Unauthorized")
        except urllib.error.HTTPError as exc:
            self.assertEqual(exc.code, 401)
            exc.close()

        # Login with valid password returns a session cookie.
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

        cookie_val = cookie.split(";")[0]

        # Authenticated GET /api/stats succeeds.
        auth_req = urllib.request.Request(
            f"{self.base_url}/api/stats",
            headers={"Cookie": cookie_val},
        )
        with urllib.request.urlopen(auth_req) as res:
            self.assertEqual(res.status, 200)
            data = json.loads(res.read().decode())
            self.assertEqual(data["status"], "online")

        # Authenticated POST /api/settings updates configuration.
        settings_req = urllib.request.Request(
            f"{self.base_url}/api/settings",
            data=json.dumps({"nut_host": "192.0.2.55", "poll_interval": 3.5}).encode("utf-8"),
            headers={"Content-Type": "application/json", "Cookie": cookie_val},
        )
        with urllib.request.urlopen(settings_req) as res:
            self.assertEqual(res.status, 200)
            resp_data = json.loads(res.read().decode())
            self.assertTrue(resp_data["success"])
            self.assertEqual(self.config.get("nut_host"), "192.0.2.55")
            self.assertEqual(self.config.get("poll_interval"), 3.5)

        # Logout revokes the active session.
        logout_req = urllib.request.Request(
            f"{self.base_url}/api/logout",
            data=b"",
            headers={"Cookie": cookie_val},
        )
        with urllib.request.urlopen(logout_req) as res:
            self.assertEqual(res.status, 200)
            clear_cookie = res.headers.get("Set-Cookie")
            self.assertIn("Max-Age=0", clear_cookie)

        # Subsequent request with revoked cookie fails with 401.
        try:
            urllib.request.urlopen(auth_req)
            self.fail("Expected 401 Unauthorized after logout")
        except urllib.error.HTTPError as exc:
            self.assertEqual(exc.code, 401)
            exc.close()

        # Reset authentication for remaining tests.
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
        except urllib.error.HTTPError as exc:
            self.assertEqual(exc.code, 413)
            exc.close()

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
