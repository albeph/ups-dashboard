"""HTTP request routing, static file serving, and REST API controllers."""

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from .collector import ActivityTracker, NUTDataCache
from .config import ConfigManager
from .constants import APP_VERSION, LOCALES_DIR, STATIC_DIR
from .security import SessionManager, encrypt_secret, hash_password

logger = logging.getLogger("ups-dashboard.router")


@dataclass
class Response:
    """Encapsulates an HTTP response."""
    status: int = 200
    body: bytes = b""
    content_type: str = "application/json; charset=utf-8"
    headers: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def json(cls, data: Any, status: int = 200, extra_headers: Optional[Dict[str, str]] = None) -> "Response":
        payload = json.dumps(data).encode("utf-8")
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Content-Length": str(len(payload)),
            "Cache-Control": "no-store, no-cache, must-revalidate",
        }
        if extra_headers:
            headers.update(extra_headers)
        return cls(status=status, body=payload, content_type=headers["Content-Type"], headers=headers)

    @classmethod
    def static(cls, content: bytes, content_type: str, extra_headers: Optional[Dict[str, str]] = None) -> "Response":
        headers = {
            "Content-Type": content_type,
            "Content-Length": str(len(content)),
        }
        if extra_headers:
            headers.update(extra_headers)
        return cls(status=200, body=content, content_type=content_type, headers=headers)

    @classmethod
    def not_found(cls, message: str = "File Not Found") -> "Response":
        payload = message.encode("utf-8")
        headers = {
            "Content-Type": "text/plain; charset=utf-8",
            "Content-Length": str(len(payload)),
        }
        return cls(status=404, body=payload, content_type=headers["Content-Type"], headers=headers)

    @classmethod
    def unauthorized(cls) -> "Response":
        return cls.json({"error": "Unauthorized", "auth_required": True}, status=401)


class Router:
    """Dispatches HTTP requests to corresponding controller actions."""

    def __init__(
        self,
        config: ConfigManager,
        cache: NUTDataCache,
        tracker: ActivityTracker,
        session_manager: SessionManager,
        static_dir: str = STATIC_DIR,
        locales_dir: str = LOCALES_DIR,
        version: str = APP_VERSION,
    ):
        self.config = config
        self.cache = cache
        self.tracker = tracker
        self.session_manager = session_manager
        self.static_dir = os.path.abspath(static_dir)
        self.locales_dir = os.path.abspath(locales_dir)
        self.version = version

    def is_authenticated(self, cookie_header: Optional[str], auth_header: Optional[str]) -> bool:
        """Determines if the request contains valid authentication credentials."""
        if not self.config.is_auth_required():
            return True

        cookie_token = self.session_manager.extract_token_from_cookie(cookie_header)
        if cookie_token and self.session_manager.is_valid(cookie_token):
            return True

        bearer_token = self.session_manager.extract_token_from_auth(auth_header)
        if bearer_token and self.session_manager.is_valid(bearer_token):
            return True

        return False

    def handle_get(self, path: str, cookie_header: Optional[str], auth_header: Optional[str]) -> Response:
        """Route GET requests."""
        if path == "/api/stats":
            return self._handle_get_stats(cookie_header, auth_header)
        elif path == "/api/version":
            return Response.json({"version": self.version})
        elif path == "/api/settings":
            return self._handle_get_settings(cookie_header, auth_header)
        elif path == "/api/health":
            return Response.json({"status": "ok", "version": self.version})
        elif path == "/api/locales":
            return self._handle_get_locales()
        elif path == "/" or path == "/index.html":
            return self._serve_index()
        else:
            return self._serve_static(path)

    def handle_post(self, path: str, body: bytes, cookie_header: Optional[str], auth_header: Optional[str]) -> Response:
        """Route POST requests."""
        if path == "/api/login":
            return self._handle_post_login(body)
        elif path == "/api/logout":
            return self._handle_post_logout(cookie_header)
        elif path == "/api/settings":
            return self._handle_post_settings(body, cookie_header, auth_header)
        return Response.not_found("Not Found")

    # -------------------------------------------------------------------------
    # Controllers: GET Handlers
    # -------------------------------------------------------------------------
    def _handle_get_stats(self, cookie_header: Optional[str], auth_header: Optional[str]) -> Response:
        if not self.is_authenticated(cookie_header, auth_header):
            return Response.unauthorized()

        was_suspended = self.tracker.record_activity()
        if was_suspended:
            self.tracker.wait_for_fresh_poll(timeout=2.0)

        data = self.cache.get_data()
        data.update({
            "auth_required": self.config.is_auth_required(),
            "version": self.version,
            "nut_host": self.config.get("nut_host"),
            "nut_port": self.config.get("nut_port"),
            "ups_name": self.config.get("ups_name"),
            "poll_interval": self.config.get("poll_interval", 2.0),
        })
        return Response.json(data)

    def _handle_get_settings(self, cookie_header: Optional[str], auth_header: Optional[str]) -> Response:
        if not self.is_authenticated(cookie_header, auth_header):
            return Response.unauthorized()

        was_suspended = self.tracker.record_activity()
        if was_suspended:
            self.tracker.wait_for_fresh_poll(timeout=2.0)

        current = self.config.get_all()
        telemetry = self.cache.get_data()

        settings_payload = {
            "nut_host": current["nut_host"],
            "nut_port": current["nut_port"],
            "ups_name": current["ups_name"],
            "nut_user": current["nut_user"],
            "has_nut_password": bool(self.config.get_nut_password()),
            "has_dashboard_password": self.config.is_auth_required(),
            "poll_interval": current["poll_interval"],
            "version": self.version,
            "server_status": telemetry["status"],
            "ups_status": telemetry.get("ups_status", ""),
            "ups_status_raw": telemetry.get("ups_status_raw", ""),
            "ups_model": telemetry.get("ups_model", ""),
            "error_message": telemetry.get("error_message", ""),
            "last_update": telemetry.get("last_update", 0),
            "load": telemetry.get("load", 0),
            "battery": telemetry.get("battery", 0),
            "watts": telemetry.get("watts", None),
            "nominal_watts": telemetry.get("nominal_watts", None),
            "voltage": telemetry.get("voltage", None),
        }
        return Response.json(settings_payload)

    def _handle_get_locales(self) -> Response:
        available = []
        if os.path.isdir(self.locales_dir):
            for fname in sorted(os.listdir(self.locales_dir)):
                if fname.endswith(".json"):
                    code = fname[:-5]
                    file_path = os.path.join(self.locales_dir, fname)
                    try:
                        with open(file_path, "r", encoding="utf-8") as lf:
                            data = json.load(lf)
                            meta = data.get("_meta", {})
                            available.append({
                                "code": meta.get("code", code),
                                "name": meta.get("name", code.upper()),
                                "flag": meta.get("flag", "🌐"),
                            })
                    except Exception as e:
                        logger.warning(f"Error loading locale {fname}: {e}")
                        available.append({"code": code, "name": code.upper(), "flag": "🌐"})
        return Response.json({"locales": available, "default": "en"})

    def _serve_index(self) -> Response:
        index_path = os.path.join(self.static_dir, "index.html")
        try:
            with open(index_path, "rb") as f:
                content = f.read()
            return Response.static(content, "text/html; charset=utf-8", {"Cache-Control": "no-cache"})
        except FileNotFoundError:
            return Response.not_found("File Not Found")

    def _serve_static(self, req_path: str) -> Response:
        safe_path = os.path.abspath(os.path.join(self.static_dir, req_path.lstrip("/")))
        # Directory traversal prevention
        try:
            common = os.path.commonpath([self.static_dir, safe_path])
            if common != self.static_dir or not os.path.isfile(safe_path):
                return Response.not_found("Not Found")
        except ValueError:
            return Response.not_found("Not Found")

        content_type = "text/plain; charset=utf-8"
        extra_headers = {}

        if safe_path.endswith(".css"):
            content_type = "text/css; charset=utf-8"
        elif safe_path.endswith(".js"):
            content_type = "application/javascript; charset=utf-8"
            if os.path.basename(safe_path) == "sw.js":
                extra_headers["Service-Worker-Allowed"] = "/"
                extra_headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        elif safe_path.endswith(".svg"):
            content_type = "image/svg+xml"
        elif safe_path.endswith(".png"):
            content_type = "image/png"
        elif safe_path.endswith(".ico"):
            content_type = "image/x-icon"
        elif safe_path.endswith(".json") or safe_path.endswith(".webmanifest"):
            content_type = (
                "application/manifest+json; charset=utf-8"
                if "manifest" in safe_path
                else "application/json; charset=utf-8"
            )
        elif safe_path.endswith(".md"):
            content_type = "text/markdown; charset=utf-8"

        try:
            with open(safe_path, "rb") as f:
                content = f.read()
            return Response.static(content, content_type, extra_headers)
        except Exception as e:
            logger.warning(f"Error serving static file {safe_path}: {e}")
            return Response.not_found("Not Found")

    # -------------------------------------------------------------------------
    # Controllers: POST Handlers
    # -------------------------------------------------------------------------
    def _handle_post_login(self, body: bytes) -> Response:
        if not self.config.is_auth_required():
            return Response.json({"success": True, "message": "No password configured"})

        try:
            req_data = json.loads(body.decode("utf-8")) if body else {}
            provided_pwd = req_data.get("password", "")

            if self.config.verify_dashboard_password(provided_pwd):
                self.tracker.record_activity()
                new_token = self.session_manager.create_session()
                cookie_val = self.session_manager.build_cookie_header(new_token)
                logger.info("Successful authentication login.")
                return Response.json({"success": True}, extra_headers={"Set-Cookie": cookie_val})
            else:
                return Response.json({"success": False, "error": "Password errata"}, status=401)
        except Exception:
            return Response.json({"success": False, "error": "Richiesta non valida"}, status=400)

    def _handle_post_logout(self, cookie_header: Optional[str]) -> Response:
        token = self.session_manager.extract_token_from_cookie(cookie_header)
        if token:
            self.session_manager.invalidate(token)

        clear_cookie = self.session_manager.build_clear_cookie_header()
        return Response.json({"success": True}, extra_headers={"Set-Cookie": clear_cookie})

    def _handle_post_settings(
        self, body: bytes, cookie_header: Optional[str], auth_header: Optional[str]
    ) -> Response:
        if not self.is_authenticated(cookie_header, auth_header):
            return Response.unauthorized()

        self.tracker.record_activity()

        try:
            req_data = json.loads(body.decode("utf-8")) if body else {}
            updates: Dict[str, Any] = {}

            if "nut_host" in req_data and req_data["nut_host"].strip():
                updates["nut_host"] = req_data["nut_host"].replace("\r", "").replace("\n", "").strip()

            if "nut_port" in req_data:
                try:
                    port_val = int(req_data["nut_port"])
                    if 1 <= port_val <= 65535:
                        updates["nut_port"] = port_val
                except (ValueError, TypeError):
                    pass

            if "ups_name" in req_data and req_data["ups_name"].strip():
                updates["ups_name"] = req_data["ups_name"].replace("\r", "").replace("\n", "").strip()

            if "nut_user" in req_data:
                updates["nut_user"] = req_data["nut_user"].replace("\r", "").replace("\n", "").strip()

            if "poll_interval" in req_data:
                try:
                    p_val = float(req_data["poll_interval"])
                    if p_val >= 0.5:
                        updates["poll_interval"] = round(p_val, 1)
                except (ValueError, TypeError):
                    pass

            # Update NUT password only if provided
            if "nut_password" in req_data and req_data["nut_password"] != "":
                updates["nut_password_encrypted"] = encrypt_secret(
                    req_data["nut_password"], self.config.secret_key
                )
            elif req_data.get("clear_nut_password"):
                updates["nut_password_encrypted"] = ""

            # Update dashboard password only if provided
            if "new_dashboard_password" in req_data and req_data["new_dashboard_password"] != "":
                updates["dashboard_password_hash"] = hash_password(
                    req_data["new_dashboard_password"]
                )
            elif req_data.get("clear_dashboard_password"):
                updates["dashboard_password_hash"] = ""

            if updates:
                self.config.update(updates)
                logger.info("Saved new settings from Web UI.")

            return Response.json({"success": True, "message": "Impostazioni salvate"})
        except Exception as e:
            logger.error(f"Error saving settings: {e}")
            return Response.json({"success": False, "error": str(e)}, status=400)
