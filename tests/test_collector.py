"""Tests for dashboard.collector module."""

import os
import sys
import time
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "image")))

from dashboard.collector import ActivityTracker, NUTDataCache
from dashboard.nut import NutMetrics


class TestCollector(unittest.TestCase):

    def test_cache_update_and_offline(self):
        cache = NUTDataCache()
        self.assertEqual(cache.status, "connecting")

        metrics = NutMetrics(
            status="online",
            watts=350,
            nominal_watts=1000,
            load=35,
            battery=100,
            voltage=231.0,
            ups_status="Rete elettrica",
            ups_status_raw="OL",
            ups_model="APC Smart-UPS",
            raw_vars={"ups.status": "OL", "battery.charge": "100"},
        )
        cache.update_metrics(metrics)
        data = cache.get_data()
        self.assertEqual(data["status"], "online")
        self.assertEqual(data["watts"], 350)
        self.assertEqual(data["load"], 35)
        self.assertEqual(data["nut_raw_vars"]["ups.status"], "OL")
        self.assertGreater(data["last_update"], 0)

        # Mark offline
        cache.update_offline("Connection refused")
        data_off = cache.get_data()
        self.assertEqual(data_off["status"], "offline")
        self.assertEqual(data_off["error_message"], "Connection refused")
        self.assertEqual(data_off["nut_raw_vars"], {})

        cache.update_unconfigured("Configuration required")
        data_cfg = cache.get_data()
        self.assertEqual(data_cfg["status"], "unconfigured")
        self.assertEqual(data_cfg["error_message"], "Configuration required")

    def test_activity_tracker_idle_and_suspension(self):
        tracker = ActivityTracker()

        # Idle timeout with poll_interval 2.0 is max(10.0, 5.0) = 10.0
        self.assertEqual(tracker.get_idle_timeout(2.0), 10.0)
        # Idle timeout with poll_interval 10.0 is max(10.0, 25.0) = 25.0
        self.assertEqual(tracker.get_idle_timeout(10.0), 25.0)

        # Just created -> not idle
        self.assertFalse(tracker.is_idle(2.0))

        # Manually alter last activity to simulate idle
        tracker._last_activity = time.time() - 15.0
        self.assertTrue(tracker.is_idle(2.0))

        # Record activity -> should wake up
        tracker.mark_suspended()
        was_suspended = tracker.record_activity()
        self.assertTrue(was_suspended)
        self.assertFalse(tracker.is_idle(2.0))


if __name__ == "__main__":
    unittest.main()
