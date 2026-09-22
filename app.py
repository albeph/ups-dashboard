#!/usr/bin/env python3
"""
UPS Web Dashboard - Lightweight NUT Web Monitor
================================================
A self-contained, zero-dependency web interface for Network UPS Tools (NUT).
Runs efficiently on any Docker host (from low-power SBCs to full servers).
"""

import hashlib
import hmac
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
    APP_VERSION = "1.1.0"

DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
KEY_FILE = os.path.join(DATA_DIR, ".secret_key")


def get_or_create_app_key() -> bytes:
    """Retrieve existing 32-byte symmetric master key or generate and persist one with 0600 permissions."""
    if os.path.isfile(KEY_FILE):
        try:
            with open(KEY_FILE, "rb") as f:
                key = f.read()
            if len(key) == 32:
                return key
        except Exception as e:
            logger.warning(f"Failed to read secret key from {KEY_FILE}: {e}")

    key = secrets.token_bytes(32)
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        mode = 0o600
        fd = os.open(KEY_FILE, flags, mode)
        with open(fd, "wb") as f:
            f.write(key)
        try:
            os.chmod(KEY_FILE, 0o600)
        except Exception:
            pass
        logger.info("Generated and saved new application secret key (chmod 0600).")
    except Exception as e:
        logger.error(f"Failed to persist application secret key: {e}")
    return key


def hash_password(plain: str) -> str:
    """Hash password using PBKDF2-HMAC-SHA256 with a unique random 16-byte salt."""
    if not plain:
        return ""
    salt = secrets.token_bytes(16)
    iterations = 100_000
    dk = hashlib.pbkdf2_hmac("sha256", plain.encode("utf-8"), salt, iterations)
    return f"pbkdf2:sha256:{iterations}${salt.hex()}${dk.hex()}"


def verify_password(plain: str, hashed: str) -> bool:
    """Verify plain password against a stored PBKDF2 hash using constant-time comparison."""
    if not hashed or not plain:
        return False
    try:
        parts = hashed.split("$")
        if len(parts) != 3:
            return False
        method_part, salt_hex, hash_hex = parts
        method, alg, iters_str = method_part.split(":")
        if method != "pbkdf2" or alg != "sha256":
            return False
        iterations = int(iters_str)
        salt = bytes.fromhex(salt_hex)
        expected_dk = bytes.fromhex(hash_hex)
        actual_dk = hashlib.pbkdf2_hmac("sha256", plain.encode("utf-8"), salt, iterations)
        return secrets.compare_digest(actual_dk, expected_dk)
    except Exception:
        return False


def encrypt_secret(plain: str, key: bytes) -> str:
    """Encrypt reversible secret using HMAC-SHA256 authenticated CTR stream cipher."""
    if not plain:
        return ""
    data = plain.encode("utf-8")
    nonce = secrets.token_bytes(16)
    keystream = bytearray()
    counter = 0
    while len(keystream) < len(data):
        block = hmac.new(key, b"keystream:" + nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest()
        keystream.extend(block)
        counter += 1
    ciphertext = bytes(b ^ k for b, k in zip(data, keystream[:len(data)]))
    tag = hmac.new(key, b"auth:" + nonce + ciphertext, hashlib.sha256).digest()
    return f"enc:v1:{nonce.hex()}:{ciphertext.hex()}:{tag.hex()}"


def decrypt_secret(enc_str: str, key: bytes) -> str:
    """Decrypt reversible secret with HMAC-SHA256 verification."""
    if not enc_str:
        return ""
    try:
        parts = enc_str.split(":")
        if len(parts) != 5 or parts[0] != "enc" or parts[1] != "v1":
            return ""
        nonce = bytes.fromhex(parts[2])
        ciphertext = bytes.fromhex(parts[3])
        expected_tag = bytes.fromhex(parts[4])
        tag = hmac.new(key, b"auth:" + nonce + ciphertext, hashlib.sha256).digest()
        if not secrets.compare_digest(tag, expected_tag):
            logger.warning("Decryption failed: auth tag mismatch")
            return ""
        keystream = bytearray()
        counter = 0
        while len(keystream) < len(ciphertext):
            block = hmac.new(key, b"keystream:" + nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest()
            keystream.extend(block)
            counter += 1
        plain = bytes(b ^ k for b, k in zip(ciphertext, keystream[:len(ciphertext)]))
        return plain.decode("utf-8", errors="replace")
    except Exception as e:
        logger.warning(f"Error during secret decryption: {e}")
        return ""


class ConfigManager:
    """Manages application settings with persistent JSON storage, password hashing, and encrypted secrets."""

    def __init__(self, filepath):
        self.filepath = filepath
        self.lock = threading.Lock()
        self.reload_event = threading.Event()
        self.secret_key = get_or_create_app_key()
        self.config = self._load_initial()

    def _load_initial(self):
        # Defaults derived from environment variables
        nut_pwd_env = os.getenv("NUT_PASSWORD", "").strip()
        nut_pwd_file = os.getenv("NUT_PASSWORD_FILE", "").strip()
        if nut_pwd_file and os.path.isfile(nut_pwd_file):
            try:
                with open(nut_pwd_file, "r", encoding="utf-8") as f:
                    nut_pwd_env = f.read().strip()
            except Exception as e:
                logger.warning(f"Failed to read NUT_PASSWORD_FILE ({nut_pwd_file}): {e}")

        dash_pwd_env = os.getenv("DASHBOARD_PASSWORD", "").strip()
        dash_hash = ""
        if dash_pwd_env:
            if dash_pwd_env.startswith("pbkdf2:sha256:"):
                dash_hash = dash_pwd_env
            else:
                dash_hash = hash_password(dash_pwd_env)

        nut_enc = ""
        if nut_pwd_env:
            nut_enc = encrypt_secret(nut_pwd_env, self.secret_key)

        defaults = {
            "nut_host": os.getenv("NUT_HOST", "127.0.0.1").strip(),
            "nut_port": int(os.getenv("NUT_PORT", "3493")),
            "ups_name": os.getenv("UPS_NAME", "ups").strip(),
            "nut_user": os.getenv("NUT_USER", "").strip(),
            "nut_password_encrypted": nut_enc,
            "dashboard_password_hash": dash_hash,
            "poll_interval": float(os.getenv("POLL_INTERVAL", "2.0")),
            "port": int(os.getenv("PORT", "8080")),
        }

        needs_save = False

        # Override with persisted config.json if present
        if os.path.isfile(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    saved = json.load(f)

                # Check for legacy plaintext passwords to migrate
                if "dashboard_password" in saved:
                    plain_dash = str(saved.pop("dashboard_password", "")).strip()
                    if plain_dash:
                        defaults["dashboard_password_hash"] = hash_password(plain_dash)
                    needs_save = True
                    logger.info("Migrated plaintext dashboard_password to PBKDF2 hash.")

                if "nut_password" in saved:
                    plain_nut = str(saved.pop("nut_password", ""))
                    if plain_nut:
                        defaults["nut_password_encrypted"] = encrypt_secret(plain_nut, self.secret_key)
                    needs_save = True
                    logger.info("Migrated plaintext nut_password to encrypted secret.")

                for k, v in saved.items():
                    if k in defaults:
                        defaults[k] = v
                logger.info(f"Loaded persistent configuration from {self.filepath}")
            except Exception as e:
                logger.warning(f"Failed to read {self.filepath}: {e}")

        # Set strict permissions and save migrated config if needed
        if needs_save:
            try:
                self._save_to_disk(defaults)
                logger.info("Cleaned plaintext credentials and persisted secured config.json.")
            except Exception as e:
                logger.error(f"Failed to persist migrated configuration: {e}")
        elif os.path.isfile(self.filepath):
            try:
                os.chmod(self.filepath, 0o600)
            except Exception:
                pass

        return defaults

    def _save_to_disk(self, config_dict):
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        mode = 0o600
        fd = os.open(self.filepath, flags, mode)
        with open(fd, "w", encoding="utf-8") as f:
            json.dump(config_dict, f, indent=2)
        try:
            os.chmod(self.filepath, 0o600)
        except Exception:
            pass

    def get(self, key, default=None):
        with self.lock:
            return self.config.get(key, default)

    def get_nut_password(self) -> str:
        """Returns the decrypted NUT password for socket communication."""
        with self.lock:
            enc = self.config.get("nut_password_encrypted", "")
            if enc:
                return decrypt_secret(enc, self.secret_key)
            return ""

    def is_auth_required(self) -> bool:
        """Returns True if dashboard password protection is active."""
        with self.lock:
            return bool(self.config.get("dashboard_password_hash"))

    def verify_dashboard_password(self, candidate: str) -> bool:
        """Verifies candidate password against stored PBKDF2 hash."""
        with self.lock:
            dash_hash = self.config.get("dashboard_password_hash", "")
            if not dash_hash:
                return True
            return verify_password(candidate, dash_hash)

    def get_all(self):
        with self.lock:
            return dict(self.config)

    def update(self, new_values):
        with self.lock:
            for k, v in new_values.items():
                if k in self.config and v is not None:
                    self.config[k] = v

            try:
                self._save_to_disk(self.config)
                logger.info("Configuration updated and saved to disk with 0600 permissions.")
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
                "auth_required": config.is_auth_required(),
                "version": APP_VERSION,
                "nut_host": config.get("nut_host"),
                "nut_port": config.get("nut_port"),
                "ups_name": config.get("ups_name"),
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
        nut_pwd = config.get_nut_password()
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
        if not config.is_auth_required():
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
                "has_nut_password": bool(config.get_nut_password()),
                "has_dashboard_password": config.is_auth_required(),
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
            if not config.is_auth_required():
                self.send_json({"success": True, "message": "No password configured"})
                return

            try:
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length)
                req_data = json.loads(body.decode("utf-8"))
                provided_pwd = req_data.get("password", "")

                if config.verify_dashboard_password(provided_pwd):
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
                    updates["nut_password_encrypted"] = encrypt_secret(req_data["nut_password"], config.secret_key)
                elif req_data.get("clear_nut_password"):
                    updates["nut_password_encrypted"] = ""

                # Update dashboard password only if provided
                if "new_dashboard_password" in req_data and req_data["new_dashboard_password"] != "":
                    updates["dashboard_password_hash"] = hash_password(req_data["new_dashboard_password"])
                elif req_data.get("clear_dashboard_password"):
                    updates["dashboard_password_hash"] = ""

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

    if config.is_auth_required():
        logger.info("Password protection: ENABLED (Cryptographic PBKDF2-HMAC-SHA256)")
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
