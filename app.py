#!/usr/bin/env python3
"""
UPS Web Dashboard - Lightweight NUT Web Monitor
================================================
A self-contained, zero-dependency web interface for Network UPS Tools (NUT).
Runs efficiently on any Docker host (from low-power SBCs to full servers).
"""

import http.cookies
import json
import logging
import os
import re
import secrets
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ups-dashboard")

# Determine project base directory and read VERSION
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VERSION_FILE = os.path.join(BASE_DIR, "VERSION")
try:
    with open(VERSION_FILE, "r", encoding="utf-8") as vf:
        APP_VERSION = vf.read().strip()
except Exception:
    APP_VERSION = "1.0.0"

DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")


class ConfigManager:
    """Manages application settings with persistent JSON storage."""

    def __init__(self, filepath):
        self.filepath = filepath
        self.lock = threading.Lock()
        self.reload_event = threading.Event()
        self.config = self._load_initial()

    def _load_initial(self):
        # Defaults derived from environment variables
        defaults = {
            "nut_host": os.getenv("NUT_HOST", "127.0.0.1").strip(),
            "nut_port": int(os.getenv("NUT_PORT", "3493")),
            "ups_name": os.getenv("UPS_NAME", "ups").strip(),
            "nut_user": os.getenv("NUT_USER", "").strip(),
            "nut_password": os.getenv("NUT_PASSWORD", "").strip(),
            "dashboard_password": os.getenv("DASHBOARD_PASSWORD", "").strip(),
            "poll_interval": float(os.getenv("POLL_INTERVAL", "2.0")),
            "port": int(os.getenv("PORT", "8080")),
        }

        # Override with persisted config.json if present
        if os.path.isfile(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    for k, v in saved.items():
                        if k in defaults:
                            defaults[k] = v
                logger.info(f"Loaded persistent configuration from {self.filepath}")
            except Exception as e:
                logger.warning(f"Failed to read {self.filepath}: {e}")

        return defaults

    def get(self, key, default=None):
        with self.lock:
            return self.config.get(key, default)

    def get_all(self):
        with self.lock:
            return dict(self.config)

    def update(self, new_values):
        with self.lock:
            for k, v in new_values.items():
                if k in self.config and v is not None:
                    self.config[k] = v

            try:
                with open(self.filepath, "w", encoding="utf-8") as f:
                    json.dump(self.config, f, indent=2)
                logger.info("Configuration updated and saved to disk.")
            except Exception as e:
                logger.error(f"Failed to save configuration: {e}")

        self.reload_event.set()


config = ConfigManager(CONFIG_FILE)

# Session storage (in-memory)
ACTIVE_SESSIONS = set()
SESSION_LOCK = threading.Lock()
COOKIE_NAME = "ups_dashboard_session"


class NUTDataCache:
    """Thread-safe cache holding real-time telemetry from NUT daemon."""

    def __init__(self):
        self.lock = threading.Lock()
        self.status = "connecting"
        self.watts = None
        self.load = 0
        self.battery = 100
        self.last_update = 0
        self.error_message = ""

    def update(self, status, watts, load, battery, error_message=""):
        with self.lock:
            self.status = status
            self.watts = watts
            self.load = load
            self.battery = battery
            self.error_message = error_message
            self.last_update = time.time()

    def get_data(self):
        with self.lock:
            return {
                "status": self.status,
                "watts": self.watts,
                "load": self.load,
                "battery": self.battery,
                "last_update": self.last_update,
                "error_message": self.error_message,
                "auth_required": bool(config.get("dashboard_password")),
                "version": APP_VERSION,
            }


cache = NUTDataCache()


def parse_nut_var(line):
    """
    Parses a NUT protocol response line:
    VAR <upsname> <varname> "<value>"
    """
    match = re.match(r'^VAR\s+[^\s]+\s+[^\s]+\s+"?([^"\r\n]*)"?', line.strip())
    if match:
        return match.group(1)
    return None


def poll_nut_daemon():
    """Background worker that continuously queries NUT via raw TCP socket."""
    while True:
        nut_host = config.get("nut_host")
        nut_port = config.get("nut_port")
        ups_name = config.get("ups_name")
        nut_user = config.get("nut_user")
        nut_pwd = config.get("nut_password")
        poll_int = config.get("poll_interval")

        config.reload_event.clear()

        try:
            with socket.create_connection((nut_host, nut_port), timeout=3.0) as sock:
                sock_file = sock.makefile("r", encoding="utf-8", errors="replace")

                # Optional NUT authentication
                if nut_user and nut_pwd:
                    sock.sendall(f"USERNAME {nut_user}\n".encode("utf-8"))
                    sock_file.readline()
                    sock.sendall(f"PASSWORD {nut_pwd}\n".encode("utf-8"))
                    sock_file.readline()

                def query_var(var_name):
                    cmd = f"GET VAR {ups_name} {var_name}\n"
                    sock.sendall(cmd.encode("utf-8"))
                    res = sock_file.readline()
                    return parse_nut_var(res)

                # Query key metrics
                load_raw = query_var("ups.load")
                battery_raw = query_var("battery.charge")
                realpower_raw = query_var("ups.realpower") or query_var("output.realpower")
                nominal_raw = query_var("ups.realpower.nominal") or query_var("output.realpower.nominal")

                # Send LOGOUT
                sock.sendall(b"LOGOUT\n")

                # Parse load percentage
                load_val = float(load_raw) if load_raw and load_raw.replace(".", "", 1).isdigit() else 0.0

                # Parse battery percentage
                battery_val = float(battery_raw) if battery_raw and battery_raw.replace(".", "", 1).isdigit() else 100.0

                # Determine active power in Watts: ONLY if reported or calculated from UPS hardware!
                watts_val = None
                if realpower_raw:
                    clean = "".join(c for c in realpower_raw if c.isdigit() or c == ".")
                    if clean:
                        try:
                            watts_val = round(float(clean))
                        except ValueError:
                            pass

                if watts_val is None and nominal_raw:
                    clean_nom = "".join(c for c in nominal_raw if c.isdigit() or c == ".")
                    if clean_nom:
                        try:
                            nom_float = float(clean_nom)
                            watts_val = round((load_val * nom_float) / 100.0)
                        except ValueError:
                            pass

                cache.update("online", watts_val, round(load_val), round(battery_val))

        except Exception as e:
            cache.update("offline", None, 0, 0, error_message=str(e))

        # Wait for either interval expiration or reload trigger
        config.reload_event.wait(timeout=poll_int)


class DashboardHandler(BaseHTTPRequestHandler):
    """Zero-dependency HTTP handler for web UI and REST API."""

    def log_message(self, format, *args):
        pass

    def is_authenticated(self):
        pwd = config.get("dashboard_password")
        if not pwd:
            return True

        cookie_header = self.headers.get("Cookie")
        if cookie_header:
            cookie = http.cookies.SimpleCookie(cookie_header)
            if COOKIE_NAME in cookie:
                token = cookie[COOKIE_NAME].value
                with SESSION_LOCK:
                    if token in ACTIVE_SESSIONS:
                        return True

        auth_header = self.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
            with SESSION_LOCK:
                if token in ACTIVE_SESSIONS:
                    return True

        return False

    def send_json(self, data, status=200, extra_headers=None):
        payload = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # 1. API: Live stats
        if path == "/api/stats":
            if not self.is_authenticated():
                self.send_json({"error": "Unauthorized", "auth_required": True}, status=401)
                return
            self.send_json(cache.get_data())
            return

        # 2. API: App Version
        if path == "/api/version":
            self.send_json({"version": APP_VERSION})
            return

        # 3. API: Settings
        if path == "/api/settings":
            if not self.is_authenticated():
                self.send_json({"error": "Unauthorized", "auth_required": True}, status=401)
                return
            current = config.get_all()
            self.send_json({
                "nut_host": current["nut_host"],
                "nut_port": current["nut_port"],
                "ups_name": current["ups_name"],
                "nut_user": current["nut_user"],
                "has_nut_password": bool(current["nut_password"]),
                "has_dashboard_password": bool(current["dashboard_password"]),
                "poll_interval": current["poll_interval"],
                "version": APP_VERSION,
            })
            return

        # 4. API: Health check
        if path == "/api/health":
            self.send_json({"status": "ok", "version": APP_VERSION})
            return

        # 5. Serve Frontend (index.html)
        if path == "/" or path == "/index.html":
            index_path = os.path.join(BASE_DIR, "static", "index.html")
            try:
                with open(index_path, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(content)
                return
            except FileNotFoundError:
                self.send_error(404, "File Not Found")
                return

        # 6. Serve static files
        static_dir = os.path.join(BASE_DIR, "static")
        safe_path = os.path.normpath(os.path.join(static_dir, path.lstrip("/")))
        if safe_path.startswith(static_dir) and os.path.isfile(safe_path):
            content_type = "text/plain"
            if safe_path.endswith(".css"):
                content_type = "text/css"
            elif safe_path.endswith(".js"):
                content_type = "application/javascript"
            elif safe_path.endswith(".svg"):
                content_type = "image/svg+xml"

            with open(safe_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        self.send_error(404, "Not Found")

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # 1. API: Login
        if path == "/api/login":
            dash_pwd = config.get("dashboard_password")
            if not dash_pwd:
                self.send_json({"success": True, "message": "No password configured"})
                return

            try:
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length)
                req_data = json.loads(body.decode("utf-8"))
                provided_pwd = req_data.get("password", "")

                if secrets.compare_digest(provided_pwd, dash_pwd):
                    new_token = secrets.token_hex(24)
                    with SESSION_LOCK:
                        ACTIVE_SESSIONS.add(new_token)

                    cookie_val = f"{COOKIE_NAME}={new_token}; Path=/; Max-Age=2592000; HttpOnly; SameSite=Lax"
                    self.send_json({"success": True}, extra_headers={"Set-Cookie": cookie_val})
                    logger.info("Successful authentication login.")
                else:
                    self.send_json({"success": False, "error": "Password errata"}, status=401)
            except Exception as e:
                self.send_json({"success": False, "error": "Richiesta non valida"}, status=400)
            return

        # 2. API: Logout
        if path == "/api/logout":
            cookie_header = self.headers.get("Cookie")
            if cookie_header:
                cookie = http.cookies.SimpleCookie(cookie_header)
                if COOKIE_NAME in cookie:
                    token = cookie[COOKIE_NAME].value
                    with SESSION_LOCK:
                        ACTIVE_SESSIONS.discard(token)

            clear_cookie = f"{COOKIE_NAME}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax"
            self.send_json({"success": True}, extra_headers={"Set-Cookie": clear_cookie})
            return

        # 3. API: Save Settings
        if path == "/api/settings":
            if not self.is_authenticated():
                self.send_json({"error": "Unauthorized", "auth_required": True}, status=401)
                return

            try:
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length)
                req_data = json.loads(body.decode("utf-8"))

                updates = {}
                if "nut_host" in req_data and req_data["nut_host"].strip():
                    updates["nut_host"] = req_data["nut_host"].strip()

                if "nut_port" in req_data:
                    updates["nut_port"] = int(req_data["nut_port"])

                if "ups_name" in req_data and req_data["ups_name"].strip():
                    updates["ups_name"] = req_data["ups_name"].strip()

                if "nut_user" in req_data:
                    updates["nut_user"] = req_data["nut_user"].strip()

                # Update NUT password only if provided
                if "nut_password" in req_data and req_data["nut_password"] != "":
                    updates["nut_password"] = req_data["nut_password"]

                # Update dashboard password only if provided
                if "new_dashboard_password" in req_data and req_data["new_dashboard_password"] != "":
                    updates["dashboard_password"] = req_data["new_dashboard_password"]

                if updates:
                    config.update(updates)
                    logger.info("Saved new settings from Web UI.")

                self.send_json({"success": True, "message": "Impostazioni salvate"})
            except Exception as e:
                logger.error(f"Error saving settings: {e}")
                self.send_json({"success": False, "error": str(e)}, status=400)
            return

        self.send_error(404, "Not Found")


def run_server():
    poller_thread = threading.Thread(target=poll_nut_daemon, daemon=True)
    poller_thread.start()

    port = config.get("port", 8080)
    server_address = ("0.0.0.0", port)
    httpd = ThreadingHTTPServer(server_address, DashboardHandler)
    logger.info(f"UPS Web Dashboard v{APP_VERSION} running on http://0.0.0.0:{port}")

    dash_pwd = config.get("dashboard_password")
    if dash_pwd:
        logger.info("Password protection: ENABLED")
    else:
        logger.info("Password protection: DISABLED (Open access)")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Stopping dashboard server...")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    run_server()
