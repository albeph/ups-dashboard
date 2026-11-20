"""Unit tests for the dashboard.nut module (protocol parser and TCP client)."""

import os
import socket
import sys
import threading
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "image")))

from dashboard.nut import (
    NutClient,
    NutProtocolError,
    NutProtocolParser,
    format_ups_status,
    parse_nut_error,
    parse_nut_var,
)


class TestNut(unittest.TestCase):
    """Tests for NUT text protocol parsing, status formatting, and TCP socket communication."""

    def test_parse_nut_var(self):
        self.assertEqual(parse_nut_var('VAR ups ups.status "OL CHRG"'), "OL CHRG")
        self.assertEqual(parse_nut_var('VAR mainups battery.charge "100"'), "100")
        self.assertEqual(parse_nut_var('VAR mainups input.voltage "230.4"\r\n'), "230.4")
        self.assertEqual(parse_nut_var('VAR mainups device.model "UPS Model 1400"'), "UPS Model 1400")
        self.assertIsNone(parse_nut_var("ERR UNKNOWN-UPS"))
        self.assertIsNone(parse_nut_var(""))

    def test_format_ups_status(self):
        self.assertEqual(format_ups_status("OL"), "Utility Power")
        self.assertEqual(format_ups_status("OL CHRG"), "Utility Power • Charging")
        self.assertEqual(
            format_ups_status("OB LB DISCHRG"),
            "On Battery • Low Battery (LB) • Discharging",
        )
        self.assertEqual(format_ups_status(""), "Utility Power")
        self.assertEqual(format_ups_status("UNKNOWN_FLAG"), "UNKNOWN_FLAG")

    def test_clean_numeric(self):
        self.assertEqual(NutProtocolParser.clean_numeric("230.5"), 230.5)
        self.assertEqual(NutProtocolParser.clean_numeric("42%"), 42.0)
        self.assertIsNone(NutProtocolParser.clean_numeric("N/A"))
        self.assertIsNone(NutProtocolParser.clean_numeric(None))

    def test_mock_nut_client_fetch_metrics(self):
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.bind(("127.0.0.1", 0))
        server_sock.listen(1)
        port = server_sock.getsockname()[1]

        def handle_client():
            client, _ = server_sock.accept()
            sock_file = client.makefile("r", encoding="utf-8")
            while True:
                line = sock_file.readline()
                if not line:
                    break
                line = line.strip()
                if line == "GET VAR testups ups.status":
                    client.sendall(b'VAR testups ups.status "OL CHRG"\n')
                elif line == "GET VAR testups device.model":
                    client.sendall(b'VAR testups device.model "Pro-UPS 1500"\n')
                elif line == "GET VAR testups device.mfr":
                    client.sendall(b'VAR testups device.mfr "GenericPower"\n')
                elif line == "GET VAR testups ups.load":
                    client.sendall(b'VAR testups ups.load "25.0"\n')
                elif line == "GET VAR testups battery.charge":
                    client.sendall(b'VAR testups battery.charge "95.0"\n')
                elif line == "GET VAR testups battery.charge.low":
                    client.sendall(b'VAR testups battery.charge.low "20"\n')
                elif line == "GET VAR testups battery.runtime":
                    client.sendall(b'VAR testups battery.runtime "3405"\n')
                elif line == "GET VAR testups battery.runtime.low":
                    client.sendall(b'VAR testups battery.runtime.low "300"\n')
                elif line == "GET VAR testups ups.realpower.nominal":
                    client.sendall(b'VAR testups ups.realpower.nominal "1000"\n')
                elif line == "GET VAR testups ups.realpower":
                    client.sendall(b"ERR VAR-NOT-SUPPORTED\n")
                elif line == "GET VAR testups input.voltage":
                    client.sendall(b'VAR testups input.voltage "230.5"\n')
                elif line.startswith("LOGOUT"):
                    client.sendall(b"OK Goodbye\n")
                    break
                else:
                    client.sendall(b"ERR UNKNOWN\n")
            sock_file.close()
            client.close()
            server_sock.close()

        server_thread = threading.Thread(target=handle_client, daemon=True)
        server_thread.start()

        client = NutClient(host="127.0.0.1", port=port, ups_name="testups", timeout=2.0)
        metrics = client.fetch_metrics()

        self.assertEqual(metrics.status, "online")
        self.assertEqual(metrics.load, 25)
        self.assertEqual(metrics.battery, 95)
        self.assertEqual(metrics.battery_charge_low, 20)
        self.assertEqual(metrics.battery_runtime, 3405)
        self.assertEqual(metrics.battery_runtime_low, 300)
        self.assertEqual(metrics.nominal_watts, 1000)
        # Active power derived from load (25%) * nominal power (1000W) = 250W.
        self.assertEqual(metrics.watts, 250)
        self.assertEqual(metrics.voltage, 230.5)
        self.assertEqual(metrics.ups_model, "GenericPower Pro-UPS 1500")
        self.assertEqual(metrics.ups_status, "Utility Power • Charging")

    def test_parse_nut_error(self):
        self.assertEqual(parse_nut_error("ERR UNKNOWN-UPS\n"), "UNKNOWN-UPS")
        self.assertEqual(parse_nut_error("ERR DATA-STALE\r\n"), "DATA-STALE")
        self.assertIsNone(parse_nut_error('VAR mainups ups.load "5"\n'))
        self.assertIsNone(parse_nut_error("OK\n"))

    def test_unknown_ups_raises_protocol_error(self):
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.bind(("127.0.0.1", 0))
        server_sock.listen(1)
        port = server_sock.getsockname()[1]

        def handle_client():
            client, _ = server_sock.accept()
            sock_file = client.makefile("r", encoding="utf-8")
            if sock_file.readline():
                client.sendall(b"ERR UNKNOWN-UPS\n")
            sock_file.close()
            client.close()
            server_sock.close()

        server_thread = threading.Thread(target=handle_client, daemon=True)
        server_thread.start()

        client = NutClient(host="127.0.0.1", port=port, ups_name="missing_ups", timeout=2.0)
        with self.assertRaises(NutProtocolError) as ctx:
            client.fetch_metrics()
        self.assertEqual(ctx.exception.error_code, "UNKNOWN-UPS")
        self.assertIn("UNKNOWN-UPS", str(ctx.exception))
        self.assertIn("missing_ups", str(ctx.exception))

    def test_auth_error_raises_protocol_error(self):
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.bind(("127.0.0.1", 0))
        server_sock.listen(1)
        port = server_sock.getsockname()[1]

        def handle_client():
            client, _ = server_sock.accept()
            sock_file = client.makefile("r", encoding="utf-8")
            if sock_file.readline():
                client.sendall(b"OK\n")
            if sock_file.readline():
                client.sendall(b"ERR INVALID-PASSWORD\n")
            sock_file.close()
            client.close()
            server_sock.close()

        server_thread = threading.Thread(target=handle_client, daemon=True)
        server_thread.start()

        client = NutClient(
            host="127.0.0.1",
            port=port,
            ups_name="ups",
            user="upsmon",
            password="wrong",
            timeout=2.0,
        )
        with self.assertRaises(NutProtocolError) as ctx:
            client.fetch_metrics()
        self.assertEqual(ctx.exception.error_code, "INVALID-PASSWORD")
        self.assertIn("INVALID-PASSWORD", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
