from __future__ import annotations

from typing import Any
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


_OPENER = build_opener(ProxyHandler({}), _NoRedirect)


def open_loopback(request: Request, timeout: int) -> Any:
    """Open an already-validated loopback request without proxies or redirects."""
    return _OPENER.open(request, timeout=timeout)
