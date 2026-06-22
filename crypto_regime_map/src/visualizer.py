"""HTTP visualizer for the regime map."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse

from regime import DEFAULT_SYMBOLS, build_regime_payload


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = Path(__file__).with_name("static")
DATA_DIR = PROJECT_ROOT / "data"


def serve(host: str = "127.0.0.1", port: int = 8788) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/api/regime":
                self._send_regime(parsed.query)
                return
            if parsed.path == "/health":
                self._send_json({"ok": True})
                return
            if parsed.path in {"/", "/index.html"}:
                self._send_static("index.html")
                return
            if parsed.path.startswith("/static/"):
                self._send_static(parsed.path.removeprefix("/static/"))
                return
            self.send_response(404)
            self.end_headers()

        def _send_regime(self, raw_query: str) -> None:
            query = parse_qs(raw_query)
            refresh = _query_value(query, "refresh", "0") == "1"
            interval = _query_value(query, "interval", "1d")
            try:
                payload = build_regime_payload(
                    DATA_DIR,
                    interval=interval,
                    start="2020-01-01",
                    symbols=DEFAULT_SYMBOLS,
                    refresh=refresh,
                )
                self._send_json(payload)
            except Exception as exc:  # pragma: no cover - HTTP boundary
                self._send_json({"error": str(exc)}, status=500)

        def _send_json(self, payload: dict, status: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_static(self, asset_name: str) -> None:
            if "/" in asset_name or "\\" in asset_name or asset_name.startswith("."):
                self.send_response(404)
                self.end_headers()
                return
            path = STATIC_DIR / asset_name
            try:
                body = path.read_bytes()
            except FileNotFoundError:
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", _content_type(path))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args) -> None:
            return

    server = ThreadingHTTPServer((host, port), Handler)
    try:
        server.serve_forever()
    finally:
        server.server_close()


def _query_value(query: dict, key: str, default: str) -> str:
    values = query.get(key)
    return values[0] if values else default


def _content_type(path: Path) -> str:
    if path.suffix == ".css":
        return "text/css; charset=utf-8"
    if path.suffix == ".js":
        return "text/javascript; charset=utf-8"
    if path.suffix == ".html":
        return "text/html; charset=utf-8"
    return "application/octet-stream"
