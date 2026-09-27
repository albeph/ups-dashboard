"""Tests for dashboard.config module."""

import json
import os
import stat
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "image")))

from dashboard.config import ConfigManager
from dashboard.security import KeyManager, verify_password


class TestConfig(unittest.TestCase):

    def test_default_config_creation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = os.path.join(tmpdir, "config.json")
            key_file = os.path.join(tmpdir, ".secret_key")

            cfg = ConfigManager(filepath=config_file, key_file=key_file)
            self.assertEqual(cfg.get("nut_host"), "127.0.0.1")
            self.assertEqual(cfg.get("nut_port"), 3493)
            self.assertEqual(cfg.get("ups_name"), "ups")
            self.assertFalse(cfg.is_auth_required())

    def test_migration_of_plaintext_passwords(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = os.path.join(tmpdir, "config.json")
            key_file = os.path.join(tmpdir, ".secret_key")

            # Write legacy config with plaintext passwords
            legacy_data = {
                "nut_host": "192.168.1.100",
                "dashboard_password": "PlainDashboardPassword123",
                "nut_password": "PlainNutPassword456",
            }
            with open(config_file, "w", encoding="utf-8") as f:
                json.dump(legacy_data, f)

            cfg = ConfigManager(filepath=config_file, key_file=key_file)

            # Check that migration occurred
            self.assertTrue(cfg.is_auth_required())
            self.assertTrue(cfg.verify_dashboard_password("PlainDashboardPassword123"))
            self.assertEqual(cfg.get_nut_password(), "PlainNutPassword456")

            # Check that disk file no longer contains plaintext credentials
            with open(config_file, "r", encoding="utf-8") as f:
                saved = json.load(f)
            self.assertNotIn("dashboard_password", saved)
            self.assertNotIn("nut_password", saved)
            self.assertIn("dashboard_password_hash", saved)
            self.assertIn("nut_password_encrypted", saved)

            # Check file mode (0600)
            file_mode = stat.S_IMODE(os.stat(config_file).st_mode)
            self.assertEqual(file_mode, 0o600)

    def test_update_and_reload_event(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = os.path.join(tmpdir, "config.json")
            key_file = os.path.join(tmpdir, ".secret_key")

            cfg = ConfigManager(filepath=config_file, key_file=key_file)
            self.assertFalse(cfg.reload_event.is_set())

            cfg.update({"nut_host": "10.0.0.5", "poll_interval": 5.0})
            self.assertEqual(cfg.get("nut_host"), "10.0.0.5")
            self.assertEqual(cfg.get("poll_interval"), 5.0)
            self.assertTrue(cfg.reload_event.is_set())


if __name__ == "__main__":
    unittest.main()
