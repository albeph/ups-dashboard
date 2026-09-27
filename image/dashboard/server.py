"""HTTP Server and request handler implementation."""

import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional
from urllib.parse import urlparse

from .collector import ActivityTracker, NUTDataCache, NutPoller
from .config import ConfigManager
from .constants import APP_VERSION, CONFIG_FILE, DEFAULT_PORT, KEY_FILE
from .router import Response, Router
from .security import SessionManager

logger = logging.getLogger("ups-dashboard.server")


class DashboardHandler(BaseHTTPRequestHandler):
    """Zero-dependency HTTP request handler delegating to Router."""

    router: Optional[Router] = None

    def log_message(self, format: str, *args) -> None:
        """Suppress default HTTP access logging to stderr."""
        pass

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        cookie = self.headers.get("Cookie")
        auth = self.headers.get("Authorization")
        if self.router:
            response = self.router.handle_get(parsed.path, cookie, auth)
        else:
            response = Response.not_found("Server not configured")
        self._send_response(response)

    MAX_BODY_SIZE = 1_048_576  # 1 MB maximum request body

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            content_length = int(self.headers.get("Content-Length", 0))
        except (ValueError, TypeError):
            content_length = 0

        if content_length > self.MAX_BODY_SIZE:
            self._send_response(Response.json({"error": "Payload Too Large"}, status=413))
            return

        body = self.rfile.read(content_length) if content_length > 0 else b""
        cookie = self.headers.get("Cookie")
        auth = self.headers.get("Authorization")
        if self.router:
            response = self.router.handle_post(parsed.path, body, cookie, auth)
        else:
            response = Response.not_found("Server not configured")
        self._send_response(response)

    def _send_response(self, response: Response) -> None:
        self.send_response(response.status)
        # Security headers
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")

        for k, v in response.headers.items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD" and response.body:
            self.wfile.write(response.body)


def build_app(
    config_file: str = CONFIG_FILE,
    key_file: str = KEY_FILE,
) -> tuple[ConfigManager, NUTDataCache, ActivityTracker, SessionManager, Router, NutPoller]:
    """Factory creating and wiring all application components."""
    config = ConfigManager(filepath=config_file, key_file=key_file)
    cache = NUTDataCache()
    tracker = ActivityTracker()
    session_manager = SessionManager()
    router = Router(
        config=config,
        cache=cache,
        tracker=tracker,
        session_manager=session_manager,
    )
    poller = NutPoller(config=config, cache=cache, tracker=tracker)
    return config, cache, tracker, session_manager, router, poller


def run_server(host: str = "0.0.0.0", port: Optional[int] = None) -> None:
    """Entrypoint that starts the poller thread and HTTP server loop."""
    config, cache, tracker, session_manager, router, poller = build_app()
    DashboardHandler.router = router

    poller.start()

    actual_port = port if port is not None else config.get("port", DEFAULT_PORT)
    server_address = (host, actual_port)
    httpd = ThreadingHTTPServer(server_address, DashboardHandler)

    logger.info(f"UPS Web Dashboard v{APP_VERSION} running on http://{host}:{actual_port}")
    if config.is_auth_required():
        logger.info("Password protection: ENABLED (Cryptographic PBKDF2-HMAC-SHA256)")
    else:
        logger.info("Password protection: DISABLED (Open access)")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Stopping dashboard server...")
    finally:
        poller.stop()
        httpd.server_close()
