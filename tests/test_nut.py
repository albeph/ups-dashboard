"""Tests for dashboard.nut module."""

import os
import socket
import sys
import threading
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "image")))

from dashboard.nut import NutClient, format_ups_status, parse_nut_var


class TestNut(unittest.TestCase):

    def test_parse_nut_var(self):
        self.assertEqual(parse_nut_var('VAR ups ups.status "OL CHRG"'), "OL CHRG")
        self.assertEqual(parse_nut_var('VAR apc battery.charge "100"'), "100")
        self.assertEqual(parse_nut_var('VAR apc input.voltage "230.4"\r\n'), "230.4")
        self.assertEqual(parse_nut_var('VAR apc device.model "Back-UPS XS 1400U"'), "Back-UPS XS 1400U")
        self.assertIsNone(parse_nut_var("ERR UNKNOWN-UPS"))
        self.assertIsNone(parse_nut_var(""))

    def test_format_ups_status(self):
        self.assertEqual(format_ups_status("OL"), "Rete elettrica")
        self.assertEqual(format_ups_status("OL CHRG"), "Rete elettrica • In carica")
        self.assertEqual(
            format_ups_status("OB LB DISCHRG"),
            "Su batteria (Blackout) • Batteria critica (LB) • In scarica",
        )
        self.assertEqual(format_ups_status(""), "Rete elettrica")
        self.assertEqual(format_ups_status("UNKNOWN_FLAG"), "UNKNOWN_FLAG")

    def test_mock_nut_client_fetch_metrics(self):
        # Create a mock NUT server on random free port
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.bind(("127.0.0.1", 0))
        server_sock.listen(1)
        port = server_sock.getsockname()[1]

        def handle_client():
            client, _ = server_sock.accept()
            f = client.makefile("r", encoding="utf-8")
            while True:
                line = f.readline()
                if not line:
                    break
                line = line.strip()
                if line.startswith("GET VAR testups ups.status"):
                    client.sendall(b'VAR testups ups.status "OL CHRG"\n')
                elif line.startswith("GET VAR testups device.model"):
                    client.sendall(b'VAR testups device.model "Smart-UPS 1500"\n')
                elif line.startswith("GET VAR testups device.mfr"):
                    client.sendall(b'VAR testups device.mfr "APC"\n')
                elif line.startswith("GET VAR testups ups.load"):
                    client.sendall(b'VAR testups ups.load "25.0"\n')
                elif line.startswith("GET VAR testups battery.charge"):
                    client.sendall(b'VAR testups battery.charge "95.0"\n')
                elif line.startswith("GET VAR testups ups.realpower.nominal"):
                    client.sendall(b'VAR testups ups.realpower.nominal "1000"\n')
                elif line.startswith("GET VAR testups ups.realpower"):
                    client.sendall(b'ERR VAR-NOT-SUPPORTED\n')
                elif line.startswith("GET VAR testups input.voltage"):
                    client.sendall(b'VAR testups input.voltage "230.5"\n')
                elif line.startswith("LOGOUT"):
                    client.sendall(b'OK Goodbye\n')
                    break
                else:
                    client.sendall(b'ERR UNKNOWN\n')
            client.close()
            server_sock.close()

        server_thread = threading.Thread(target=handle_client, daemon=True)
        server_thread.start()

        client = NutClient(host="127.0.0.1", port=port, ups_name="testups", timeout=2.0)
        metrics = client.fetch_metrics()

        self.assertEqual(metrics.status, "online")
        self.assertEqual(metrics.load, 25)
        self.assertEqual(metrics.battery, 95)
        self.assertEqual(metrics.nominal_watts, 1000)
        # Watts calculated from load (25%) and nominal (1000W) = 250W
        self.assertEqual(metrics.watts, 250)
        self.assertEqual(metrics.voltage, 230.5)
        self.assertEqual(metrics.ups_model, "APC Smart-UPS 1500")
        self.assertEqual(metrics.ups_status, "Rete elettrica • In carica")
        self.assertEqual(metrics.raw_vars, {})


if __name__ == "__main__":
    unittest.main()
