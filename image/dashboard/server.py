"""Zero-dependency HTTP server, request handler, and application lifecycle container."""

import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional, Tuple
from urllib.parse import urlparse

from .collector import ActivityTracker, NUTDataCache, NutPoller
from .config import ConfigManager
from .constants import APP_VERSION, CONFIG_FILE, DEFAULT_PORT, KEY_FILE
from .router import Response, Router
from .security import SessionManager

logger = logging.getLogger("ups-dashboard.server")


class DashboardHTTPServer(ThreadingHTTPServer):
    """Multi-threaded HTTP server holding an instance-scoped ``Router`` reference."""

    def __init__(
        self,
        server_address: Tuple[str, int],
        handler_class: type,
        router: Router,
    ):
        self.router = router
        super().__init__(server_address, handler_class)


class DashboardHandler(BaseHTTPRequestHandler):
    """HTTP request handler that enforces security headers and delegates to ``Router``."""

    # Optional class-level fallback for tests or subclasses that attach a router directly.
    router: Optional[Router] = None
    MAX_BODY_SIZE = 1_048_576  # 1 MiB maximum POST body size

    def log_message(self, format: str, *args) -> None:
        """Suppress noisy default stderr access logging from ``BaseHTTPRequestHandler``."""
        return

    def _get_router(self) -> Optional[Router]:
        """Resolve the router from the server instance first, falling back to class attribute."""
        server_router = getattr(self.server, "router", None)
        return server_router if server_router is not None else self.router

    def do_HEAD(self) -> None:
        """Handle HEAD requests identically to GET without writing a response body."""
        self.do_GET()

    def do_GET(self) -> None:
        """Forward GET requests to the configured ``Router``."""
        parsed = urlparse(self.path)
        cookie = self.headers.get("Cookie")
        auth = self.headers.get("Authorization")
        router = self._get_router()
        if router:
            response = router.handle_get(parsed.path, cookie, auth)
        else:
            response = Response.not_found("Server not configured")
        self._send_response(response)

    def do_POST(self) -> None:
        """Validate Content-Length limits and forward POST requests to the ``Router``."""
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
        router = self._get_router()
        if router:
            response = router.handle_post(parsed.path, body, cookie, auth)
        else:
            response = Response.not_found("Server not configured")
        self._send_response(response)

    def _send_response(self, response: Response) -> None:
        """Write status code, mandatory security headers, response headers, and body."""
        self.send_response(response.status)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")

        for header_name, header_value in response.headers.items():
            self.send_header(header_name, header_value)
        self.end_headers()
        if self.command != "HEAD" and response.body:
            self.wfile.write(response.body)


class DashboardApplication:
    """Top-level composition root managing all backend components and server lifecycle."""

    def __init__(
        self,
        config_file: str = CONFIG_FILE,
        key_file: str = KEY_FILE,
        host: str = "0.0.0.0",
        port: Optional[int] = None,
    ):
        self.config = ConfigManager(filepath=config_file, key_file=key_file)
        self.cache = NUTDataCache()
        self.tracker = ActivityTracker()
        self.session_manager = SessionManager()
        self.router = Router(
            config=self.config,
            cache=self.cache,
            tracker=self.tracker,
            session_manager=self.session_manager,
        )
        self.poller = NutPoller(
            config=self.config,
            cache=self.cache,
            tracker=self.tracker,
        )
        self.host = host
        self.port = port if port is not None else int(self.config.get("port", DEFAULT_PORT))
        self.httpd: Optional[DashboardHTTPServer] = None

    def create_http_server(self) -> DashboardHTTPServer:
        """Instantiate and bind the multi-threaded HTTP server."""
        self.httpd = DashboardHTTPServer((self.host, self.port), DashboardHandler, self.router)
        return self.httpd

    def run(self) -> None:
        """Start the background NUT poller and block serving HTTP requests until interrupted."""
        self.poller.start()
        httpd = self.create_http_server()

        logger.info("UPS Web Dashboard v%s running on http://%s:%s", APP_VERSION, self.host, self.port)
        if self.config.is_auth_required():
            logger.info("Password protection: ENABLED (PBKDF2-HMAC-SHA256)")
        else:
            logger.info("Password protection: DISABLED (Open access)")

        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            logger.info("Stopping UPS Web Dashboard server...")
        finally:
            self.stop()

    def stop(self) -> None:
        """Stop the background poller and close the listening HTTP socket."""
        self.poller.stop()
        if self.httpd is not None:
            self.httpd.server_close()
            self.httpd = None


def build_app(
    config_file: str = CONFIG_FILE,
    key_file: str = KEY_FILE,
) -> tuple[ConfigManager, NUTDataCache, ActivityTracker, SessionManager, Router, NutPoller]:
    """Factory helper returning wired application components for testing or custom runners."""
    app = DashboardApplication(config_file=config_file, key_file=key_file)
    return app.config, app.cache, app.tracker, app.session_manager, app.router, app.poller


def run_server(host: str = "0.0.0.0", port: Optional[int] = None) -> None:
    """Create a ``DashboardApplication`` instance and run it until interrupted."""
    DashboardApplication(host=host, port=port).run()
