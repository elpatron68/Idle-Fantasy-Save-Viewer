"""Application security: limits, proxy trust, headers."""

from __future__ import annotations

import os

from urllib.parse import urlparse

from flask import Flask, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix

limiter = Limiter(key_func=get_remote_address, storage_uri="memory://")

DEFAULT_MAX_UPLOAD_MB = 10
VIEWER_CREATE_LIMIT = os.environ.get("RATE_LIMIT_VIEWER_CREATE", "5 per minute")
IMPORT_LIMIT = os.environ.get("RATE_LIMIT_IMPORT", "20 per hour")


def local_viewer_disabled() -> bool:
    return os.environ.get("DISABLE_LOCAL_VIEWER", "").lower() in ("1", "true", "yes")


def trust_proxy_enabled() -> bool:
    return os.environ.get("TRUST_PROXY", "").lower() in ("1", "true", "yes")


def configure_app(flask_app: Flask) -> None:
    max_mb = int(os.environ.get("MAX_UPLOAD_MB", DEFAULT_MAX_UPLOAD_MB))
    flask_app.config["MAX_CONTENT_LENGTH"] = max_mb * 1024 * 1024

    if trust_proxy_enabled():
        flask_app.wsgi_app = ProxyFix(
            flask_app.wsgi_app,
            x_for=1,
            x_proto=1,
            x_host=1,
            x_port=1,
        )

    limiter.init_app(flask_app)

    @flask_app.after_request
    def _security_headers(response):
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'self'"
        )
        return response


def external_base_url() -> str:
    """Build public base URL (respects reverse proxy and PREFERRED_URL_SCHEME)."""
    host_url = request.host_url.rstrip("/")
    preferred = os.environ.get("PREFERRED_URL_SCHEME", "").strip().lower()
    if not preferred:
        return host_url

    # Use netloc from host_url (honours ProxyFix / X-Forwarded-Host), not request.host
    # alone, which can still include the internal upstream port behind a reverse proxy.
    netloc = urlparse(host_url).netloc
    if not netloc:
        netloc = request.host
    return f"{preferred}://{netloc}"
