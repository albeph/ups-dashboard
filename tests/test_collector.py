"""Unit tests for the dashboard.collector module (cache and activity tracker)."""

import os
import sys
import time
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "image")))

from dashboard.collector import ActivityTracker, NUTDataCache
from dashboard.nut import NutMetrics


class TestCollector(unittest.TestCase):
    """Tests for telemetry caching and demand-driven standby coordination."""

    def test_cache_update_and_offline(self):
        cache = NUTDataCache()
        self.assertEqual(cache.status, "connecting")
        self.assertEqual(cache.ups_status, "Connecting...")

        metrics = NutMetrics(
            status="online",
            watts=350,
            nominal_watts=1000,
            load=35,
            battery=100,
            voltage=231.0,
            ups_status="Utility Power",
            ups_status_raw="OL",
            ups_model="Generic UPS 1500",
            battery_charge_low=25,
            battery_runtime=3600,
            battery_runtime_low=300,
        )
        cache.update_metrics(metrics)
        data = cache.get_data()
        self.assertEqual(data["status"], "online")
        self.assertEqual(data["watts"], 350)
        self.assertEqual(data["load"], 35)
        self.assertEqual(data["battery_charge_low"], 25)
        self.assertEqual(data["battery_runtime"], 3600)
        self.assertEqual(data["battery_runtime_low"], 300)
        self.assertGreater(data["last_update"], 0)

        cache.update_offline("Connection refused")
        data_off = cache.get_data()
        self.assertEqual(data_off["status"], "offline")
        self.assertEqual(data_off["ups_status"], "Disconnected")
        self.assertEqual(data_off["error_message"], "Connection refused")
        self.assertIsNone(data_off["battery_charge_low"])
        self.assertIsNone(data_off["battery_runtime"])
        self.assertIsNone(data_off["battery_runtime_low"])

    def test_activity_tracker_idle_and_suspension(self):
        tracker = ActivityTracker()

        # Idle timeout with poll_interval 2.0 is max(10.0, 5.0) = 10.0.
        self.assertEqual(tracker.get_idle_timeout(2.0), 10.0)
        # Idle timeout with poll_interval 10.0 is max(10.0, 25.0) = 25.0.
        self.assertEqual(tracker.get_idle_timeout(10.0), 25.0)

        # Freshly initialized tracker is active, not idle.
        self.assertFalse(tracker.is_idle(2.0))

        # Backdate last activity timestamp to simulate client inactivity.
        tracker._last_activity = time.time() - 15.0
        self.assertTrue(tracker.is_idle(2.0))

        # Recording activity while suspended wakes the poller and returns True.
        tracker.mark_suspended()
        was_suspended = tracker.record_activity()
        self.assertTrue(was_suspended)
        self.assertFalse(tracker.is_idle(2.0))


if __name__ == "__main__":
    unittest.main()
