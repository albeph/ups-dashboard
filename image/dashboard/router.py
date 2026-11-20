"""HTTP routing, REST API controllers, static file serving, locale discovery, and validation."""

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .collector import ActivityTracker, NUTDataCache
from .config import ConfigManager
from .constants import APP_VERSION, LOCALES_DIR, STATIC_DIR
from .security import PasswordHasher, SessionManager

logger = logging.getLogger("ups-dashboard.router")


@dataclass
class Response:
    """Value object encapsulating an HTTP response status, headers, and body."""

    status: int = 200
    body: bytes = b""
    content_type: str = "application/json; charset=utf-8"
    headers: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def json(
        cls,
        data: Any,
        status: int = 200,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> "Response":
        """Build a non-cached JSON response."""
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
    def static(
        cls,
        content: bytes,
        content_type: str,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> "Response":
        """Build a 200 OK response for static assets."""
        headers = {
            "Content-Type": content_type,
            "Content-Length": str(len(content)),
        }
        if extra_headers:
            headers.update(extra_headers)
        return cls(status=200, body=content, content_type=content_type, headers=headers)

    @classmethod
    def not_found(cls, message: str = "File Not Found") -> "Response":
        """Build a 404 Not Found plain-text response."""
        payload = message.encode("utf-8")
        headers = {
            "Content-Type": "text/plain; charset=utf-8",
            "Content-Length": str(len(payload)),
        }
        return cls(status=404, body=payload, content_type=headers["Content-Type"], headers=headers)

    @classmethod
    def unauthorized(cls) -> "Response":
        """Build a 401 Unauthorized JSON response prompting client authentication."""
        return cls.json({"error": "Unauthorized", "auth_required": True}, status=401)


class StaticFileServer:
    """Serves static frontend assets safely with MIME detection and version injection."""

    MIME_TYPES: Dict[str, str] = {
        ".html": "text/html; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".js": "application/javascript; charset=utf-8",
        ".svg": "image/svg+xml",
        ".png": "image/png",
        ".ico": "image/x-icon",
        ".json": "application/json; charset=utf-8",
        ".webmanifest": "application/manifest+json; charset=utf-8",
        ".md": "text/markdown; charset=utf-8",
    }

    VERSION_PLACEHOLDER = b"__APP_VERSION__"

    def __init__(self, static_dir: str, locales_dir: str, version: str):
        self.static_dir = os.path.abspath(static_dir)
        self.locales_dir = os.path.abspath(locales_dir)
        self.version_bytes = version.encode("utf-8")

    def serve_index(self) -> Response:
        """Serve ``index.html`` with dynamic ``__APP_VERSION__`` substitution."""
        index_path = os.path.join(self.static_dir, "index.html")
        try:
            with open(index_path, "rb") as f:
                content = f.read().replace(self.VERSION_PLACEHOLDER, self.version_bytes)
            return Response.static(
                content,
                "text/html; charset=utf-8",
                {"Cache-Control": "no-cache"},
            )
        except FileNotFoundError:
            return Response.not_found("File Not Found")

    def serve_file(self, req_path: str) -> Response:
        """Resolve and serve a static asset while blocking directory traversal attacks."""
        safe_path = os.path.abspath(os.path.join(self.static_dir, req_path.lstrip("/")))
        if not self._is_within_static_dir(safe_path) or not os.path.isfile(safe_path):
            return Response.not_found("Not Found")

        content_type = self._resolve_content_type(safe_path)
        extra_headers = self._resolve_cache_headers(safe_path)

        try:
            with open(safe_path, "rb") as f:
                content = f.read()
            if os.path.basename(safe_path) == "sw.js":
                content = content.replace(self.VERSION_PLACEHOLDER, self.version_bytes)
            return Response.static(content, content_type, extra_headers)
        except OSError as exc:
            logger.warning("Error serving static file %s: %s", safe_path, exc)
            return Response.not_found("Not Found")

    def _is_within_static_dir(self, candidate_path: str) -> bool:
        """Verify that ``candidate_path`` resides strictly inside ``self.static_dir``."""
        try:
            return os.path.commonpath([self.static_dir, candidate_path]) == self.static_dir
        except ValueError:
            return False

    def _resolve_content_type(self, file_path: str) -> str:
        """Determine the appropriate ``Content-Type`` header from the file extension."""
        _, ext = os.path.splitext(file_path.lower())
        if ext == ".json" and "manifest" in os.path.basename(file_path).lower():
            return "application/manifest+json; charset=utf-8"
        return self.MIME_TYPES.get(ext, "text/plain; charset=utf-8")

    def _resolve_cache_headers(self, file_path: str) -> Dict[str, str]:
        """Return specialized caching headers for Service Worker and locale files."""
        headers: Dict[str, str] = {}
        if os.path.basename(file_path) == "sw.js":
            headers["Service-Worker-Allowed"] = "/"
            headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        elif file_path.startswith(self.locales_dir + os.sep):
            headers["Cache-Control"] = "no-cache"
        return headers


class LocaleRegistry:
    """Discovers available JSON translation files in the locales directory."""

    DEFAULT_LOCALE = "en"

    def __init__(self, locales_dir: str):
        self.locales_dir = os.path.abspath(locales_dir)

    def list_locales(self) -> List[Dict[str, str]]:
        """Scan ``locales_dir`` and return metadata entries sorted by filename."""
        available: List[Dict[str, str]] = []
        if not os.path.isdir(self.locales_dir):
            return available

        for filename in sorted(os.listdir(self.locales_dir)):
            if not filename.endswith(".json"):
                continue
            available.append(self._load_locale_meta(filename))
        return available

    def _load_locale_meta(self, filename: str) -> Dict[str, str]:
        """Read the ``_meta`` block from a single locale JSON file, falling back gracefully."""
        code = filename[:-5]
        file_path = os.path.join(self.locales_dir, filename)
        try:
            with open(file_path, "r", encoding="utf-8") as lf:
                data = json.load(lf)
            meta = data.get("_meta", {})
            return {
                "code": meta.get("code", code),
                "name": meta.get("name", code.upper()),
                "flag": meta.get("flag", "🌐"),
            }
        except (OSError, json.JSONDecodeError, AttributeError) as exc:
            logger.warning("Failed to load locale metadata for %s: %s", filename, exc)
            return {"code": code, "name": code.upper(), "flag": "🌐"}


class SettingsValidator:
    """Validates and sanitizes incoming ``POST /api/settings`` request payloads."""

    MIN_PORT = 1
    MAX_PORT = 65535
    MIN_POLL_INTERVAL = 0.5

    @staticmethod
    def sanitize_text(value: Any) -> str:
        """Strip CR/LF control characters and surrounding whitespace to prevent injection."""
        return str(value).replace("\r", "").replace("\n", "").strip()

    @classmethod
    def extract_updates(cls, payload: Dict[str, Any], config: ConfigManager) -> Dict[str, Any]:
        """Parse and validate setting fields, returning a clean update dictionary."""
        updates: Dict[str, Any] = {}

        if "nut_host" in payload and str(payload["nut_host"]).strip():
            updates["nut_host"] = cls.sanitize_text(payload["nut_host"])

        if "nut_port" in payload:
            try:
                port_val = int(payload["nut_port"])
                if cls.MIN_PORT <= port_val <= cls.MAX_PORT:
                    updates["nut_port"] = port_val
            except (ValueError, TypeError):
                pass

        if "ups_name" in payload and str(payload["ups_name"]).strip():
            updates["ups_name"] = cls.sanitize_text(payload["ups_name"])

        if "nut_user" in payload:
            updates["nut_user"] = cls.sanitize_text(payload["nut_user"])

        if "poll_interval" in payload:
            try:
                poll_val = float(payload["poll_interval"])
                if poll_val >= cls.MIN_POLL_INTERVAL:
                    updates["poll_interval"] = round(poll_val, 1)
            except (ValueError, TypeError):
                pass

        # Update or clear the encrypted NUT daemon password only when explicitly requested.
        if "nut_password" in payload and payload["nut_password"] != "":
            updates["nut_password_encrypted"] = config.encrypt_nut_password(
                str(payload["nut_password"])
            )
        elif payload.get("clear_nut_password"):
            updates["nut_password_encrypted"] = ""

        # Update or clear the PBKDF2 dashboard password hash only when explicitly requested.
        if "new_dashboard_password" in payload and payload["new_dashboard_password"] != "":
            updates["dashboard_password_hash"] = PasswordHasher.hash(
                str(payload["new_dashboard_password"])
            )
        elif payload.get("clear_dashboard_password"):
            updates["dashboard_password_hash"] = ""

        return updates


class Router:
    """Dispatches HTTP GET and POST requests to REST controllers or the static file server."""

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

        self.static_server = StaticFileServer(self.static_dir, self.locales_dir, self.version)
        self.locale_registry = LocaleRegistry(self.locales_dir)

    def is_authenticated(self, cookie_header: Optional[str], auth_header: Optional[str]) -> bool:
        """Return True if password protection is disabled or the request carries a valid session."""
        if not self.config.is_auth_required():
            return True

        cookie_token = self.session_manager.extract_token_from_cookie(cookie_header)
        if cookie_token and self.session_manager.is_valid(cookie_token):
            return True

        bearer_token = self.session_manager.extract_token_from_auth(auth_header)
        if bearer_token and self.session_manager.is_valid(bearer_token):
            return True

        return False

    def handle_get(
        self,
        path: str,
        cookie_header: Optional[str],
        auth_header: Optional[str],
    ) -> Response:
        """Dispatch HTTP GET requests to API endpoints or static file handlers."""
        if path == "/api/stats":
            return self._handle_get_stats(cookie_header, auth_header)
        if path == "/api/version":
            return Response.json({"version": self.version})
        if path == "/api/settings":
            return self._handle_get_settings(cookie_header, auth_header)
        if path == "/api/health":
            return Response.json({"status": "ok", "version": self.version})
        if path == "/api/locales":
            return self._handle_get_locales()
        if path in ("/", "/index.html"):
            return self.static_server.serve_index()
        return self.static_server.serve_file(path)

    def handle_post(
        self,
        path: str,
        body: bytes,
        cookie_header: Optional[str],
        auth_header: Optional[str],
    ) -> Response:
        """Dispatch HTTP POST requests to authentication and configuration endpoints."""
        if path == "/api/login":
            return self._handle_post_login(body)
        if path == "/api/logout":
            return self._handle_post_logout(cookie_header)
        if path == "/api/settings":
            return self._handle_post_settings(body, cookie_header, auth_header)
        return Response.not_found("Not Found")

    # -----------------------------------------------------------------------
    # Private Helpers & GET Controllers
    # -----------------------------------------------------------------------
    def _wake_poller_if_needed(self) -> None:
        """Record client activity and wait briefly for fresh data if the poller was in standby."""
        was_suspended = self.tracker.record_activity()
        if was_suspended:
            self.tracker.wait_for_fresh_poll(timeout=2.0)

    def _handle_get_stats(
        self,
        cookie_header: Optional[str],
        auth_header: Optional[str],
    ) -> Response:
        """Return live UPS telemetry enriched with current target metadata."""
        if not self.is_authenticated(cookie_header, auth_header):
            return Response.unauthorized()

        self._wake_poller_if_needed()

        data = self.cache.get_data()
        data.update(
            {
                "auth_required": self.config.is_auth_required(),
                "version": self.version,
                "nut_host": self.config.get("nut_host"),
                "nut_port": self.config.get("nut_port"),
                "ups_name": self.config.get("ups_name"),
                "poll_interval": self.config.get("poll_interval", 2.0),
            }
        )
        return Response.json(data)

    def _handle_get_settings(
        self,
        cookie_header: Optional[str],
        auth_header: Optional[str],
    ) -> Response:
        """Return non-sensitive configuration alongside current NUT connection diagnostics."""
        if not self.is_authenticated(cookie_header, auth_header):
            return Response.unauthorized()

        self._wake_poller_if_needed()

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
            "battery_charge_low": telemetry.get("battery_charge_low"),
            "battery_runtime": telemetry.get("battery_runtime"),
            "battery_runtime_low": telemetry.get("battery_runtime_low"),
            "watts": telemetry.get("watts"),
            "nominal_watts": telemetry.get("nominal_watts"),
            "voltage": telemetry.get("voltage"),
        }
        return Response.json(settings_payload)

    def _handle_get_locales(self) -> Response:
        """Return the auto-discovered list of available UI localization packs."""
        return Response.json(
            {
                "locales": self.locale_registry.list_locales(),
                "default": LocaleRegistry.DEFAULT_LOCALE,
            }
        )

    # -----------------------------------------------------------------------
    # POST Controllers
    # -----------------------------------------------------------------------
    def _handle_post_login(self, body: bytes) -> Response:
        """Authenticate a user password and issue an ``HttpOnly`` session cookie."""
        if not self.config.is_auth_required():
            return Response.json({"success": True, "message": "No password configured"})

        try:
            req_data = json.loads(body.decode("utf-8")) if body else {}
            provided_pwd = req_data.get("password", "")

            if self.config.verify_dashboard_password(provided_pwd):
                self.tracker.record_activity()
                new_token = self.session_manager.create_session()
                cookie_val = self.session_manager.build_cookie_header(new_token)
                logger.info("Successful dashboard login.")
                return Response.json({"success": True}, extra_headers={"Set-Cookie": cookie_val})

            return Response.json({"success": False, "error": "Invalid password"}, status=401)
        except (ValueError, UnicodeDecodeError, AttributeError):
            return Response.json({"success": False, "error": "Invalid request"}, status=400)

    def _handle_post_logout(self, cookie_header: Optional[str]) -> Response:
        """Invalidate the active session token and clear the client session cookie."""
        token = self.session_manager.extract_token_from_cookie(cookie_header)
        if token:
            self.session_manager.invalidate(token)

        clear_cookie = self.session_manager.build_clear_cookie_header()
        return Response.json({"success": True}, extra_headers={"Set-Cookie": clear_cookie})

    def _handle_post_settings(
        self,
        body: bytes,
        cookie_header: Optional[str],
        auth_header: Optional[str],
    ) -> Response:
        """Validate, sanitize, and persist updated configuration settings."""
        if not self.is_authenticated(cookie_header, auth_header):
            return Response.unauthorized()

        self.tracker.record_activity()

        try:
            req_data = json.loads(body.decode("utf-8")) if body else {}
            if not isinstance(req_data, dict):
                return Response.json({"success": False, "error": "Invalid JSON payload"}, status=400)

            updates = SettingsValidator.extract_updates(req_data, self.config)
            if updates:
                self.config.update(updates)
                logger.info("Saved updated settings from Web UI.")

            return Response.json({"success": True, "message": "Settings saved"})
        except Exception as exc:
            logger.error("Error saving settings: %s", exc)
            return Response.json({"success": False, "error": str(exc)}, status=400)
