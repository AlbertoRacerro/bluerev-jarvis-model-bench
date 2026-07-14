from __future__ import annotations

import hashlib
import json
import threading
import time
import urllib.error
import urllib.request
from contextlib import AbstractContextManager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


class WireProxyError(RuntimeError):
    pass


_HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}
_SENSITIVE_HEADERS = {"authorization", "proxy-authorization", "x-api-key"}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_json(data: bytes) -> Any:
    if not data:
        return None
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def _phase(path: str, body_json: Any) -> str:
    if path.rstrip("/").endswith("/models"):
        return "model_discovery"
    if not path.rstrip("/").endswith("/chat/completions"):
        return "other"
    messages = body_json.get("messages") if isinstance(body_json, dict) else None
    if not isinstance(messages, list):
        return "chat_unknown"
    if any(isinstance(item, dict) and item.get("role") == "tool" for item in messages):
        return "tool_followup"
    return "initial_decision"


class LoopbackWireProxy(AbstractContextManager["LoopbackWireProxy"]):
    """Capture exact OpenAI-wire JSON requests while forwarding only to local Ollama."""

    def __init__(self, trace_path: Path):
        self.trace_path = trace_path
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._request_index = 0

    @property
    def base_url(self) -> str:
        if self._server is None:
            raise WireProxyError("wire proxy is not running")
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}/v1"

    def __enter__(self) -> "LoopbackWireProxy":
        self.trace_path.parent.mkdir(parents=True, exist_ok=True)
        self.trace_path.write_text("", encoding="utf-8")
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, format: str, *args: Any) -> None:
                return

            def do_GET(self) -> None:  # noqa: N802
                self._forward()

            def do_POST(self) -> None:  # noqa: N802
                self._forward()

            def _forward(self) -> None:
                if not self.path.startswith("/v1/"):
                    self.send_error(404, "only /v1/* is allowed")
                    return
                length_raw = self.headers.get("Content-Length", "0")
                try:
                    length = int(length_raw)
                except ValueError:
                    self.send_error(400, "invalid content length")
                    return
                body = self.rfile.read(length) if length else b""
                body_json = _safe_json(body)
                with owner._lock:
                    owner._request_index += 1
                    request_index = owner._request_index

                upstream_url = f"http://127.0.0.1:11434{self.path}"
                headers: dict[str, str] = {}
                for key, value in self.headers.items():
                    lower = key.lower()
                    if lower in _HOP_BY_HOP or lower == "host":
                        continue
                    headers[key] = value
                request = urllib.request.Request(
                    upstream_url,
                    data=body if self.command == "POST" else None,
                    headers=headers,
                    method=self.command,
                )
                started = time.monotonic()
                status = 502
                response_headers: dict[str, str] = {}
                response_body = b""
                proxy_error: str | None = None
                try:
                    with urllib.request.urlopen(request, timeout=600) as response:
                        status = int(response.status)
                        response_headers = dict(response.headers.items())
                        response_body = response.read()
                except urllib.error.HTTPError as exc:
                    status = int(exc.code)
                    response_headers = dict(exc.headers.items()) if exc.headers else {}
                    response_body = exc.read()
                except Exception as exc:  # noqa: BLE001 - proxy persists evidence
                    proxy_error = f"{type(exc).__name__}: {exc}"
                    response_body = proxy_error.encode("utf-8", errors="replace")

                duration = time.monotonic() - started
                record = {
                    "schema_version": "bench.hermes-wire-request.v1",
                    "request_index": request_index,
                    "method": self.command,
                    "path": self.path,
                    "phase": _phase(self.path, body_json),
                    "request": {
                        "headers": {
                            key: ("<redacted>" if key.lower() in _SENSITIVE_HEADERS else value)
                            for key, value in self.headers.items()
                            if key.lower() not in _HOP_BY_HOP
                        },
                        "body_sha256": _sha256(body),
                        "body_size_bytes": len(body),
                        "json": body_json,
                    },
                    "response": {
                        "status": status,
                        "headers": {
                            key: value
                            for key, value in response_headers.items()
                            if key.lower() not in _HOP_BY_HOP
                        },
                        "body_sha256": _sha256(response_body),
                        "body_size_bytes": len(response_body),
                    },
                    "duration_seconds": duration,
                    "proxy_error": proxy_error,
                }
                with owner._lock:
                    with owner.trace_path.open("a", encoding="utf-8", newline="\n") as handle:
                        handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")

                self.send_response(status)
                for key, value in response_headers.items():
                    if key.lower() in _HOP_BY_HOP or key.lower() == "content-length":
                        continue
                    self.send_header(key, value)
                self.send_header("Content-Length", str(len(response_body)))
                self.end_headers()
                self.wfile.write(response_body)

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="bench2r-wire-proxy",
            daemon=True,
        )
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=10)
        self._server = None
        self._thread = None
