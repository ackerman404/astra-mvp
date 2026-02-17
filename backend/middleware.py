"""Rate limiting, request logging, and error handling middleware."""

import logging
import time
from collections import defaultdict

from fastapi import Depends, HTTPException

from backend.auth import validate_license
from backend.models import LicenseKey

logger = logging.getLogger("astra.requests")


# ---------------------------------------------------------------------------
# In-memory per-key rate limiting (PROXY-06)
# ---------------------------------------------------------------------------

# Structure: {license_key_id: [timestamp, timestamp, ...]}
_rate_limit_store: dict[int, list[float]] = defaultdict(list)


def _clean_old_entries(key_id: int, window_seconds: float = 60.0) -> None:
    """Remove timestamps older than the window to prevent memory leak."""
    cutoff = time.monotonic() - window_seconds
    _rate_limit_store[key_id] = [
        ts for ts in _rate_limit_store[key_id] if ts > cutoff
    ]


async def check_rate_limit(
    license_key: LicenseKey = Depends(validate_license),
) -> LicenseKey:
    """FastAPI dependency that enforces per-key rate limiting.

    Runs AFTER validate_license (uses its return value).
    Returns the license key object for downstream dependencies.
    """
    from backend.config import settings

    key_id = license_key.id
    now = time.monotonic()

    # Clean up expired entries
    _clean_old_entries(key_id)

    count = len(_rate_limit_store[key_id])
    if count >= settings.RATE_LIMIT_COMPLETIONS_RPM:
        # Calculate retry_after: seconds until the oldest request expires
        oldest = min(_rate_limit_store[key_id])
        retry_after = max(1, int(60.0 - (now - oldest)))
        raise HTTPException(
            status_code=429,
            detail={
                "error": {
                    "code": "rate_limited",
                    "message": "Too many requests. Please wait.",
                    "retry_after": retry_after,
                }
            },
        )

    # Record this request
    _rate_limit_store[key_id].append(now)
    return license_key


# ---------------------------------------------------------------------------
# Request logging middleware (REL-04)
# ---------------------------------------------------------------------------


class RequestLoggingMiddleware:
    """ASGI middleware that logs every request with structured fields."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.monotonic()
        status_code = 500  # Default — will be overwritten by actual response

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            latency_ms = (time.monotonic() - start) * 1000
            method = scope.get("method", "?")
            path = scope.get("path", "?")

            # Extract truncated license key from headers (first 8 chars for privacy)
            headers = dict(scope.get("headers", []))
            auth_header = headers.get(b"authorization", b"").decode(errors="replace")
            key_preview = "none"
            if auth_header.startswith("Bearer ") and len(auth_header) > 15:
                key_preview = auth_header[7:15] + "..."

            # Choose log level based on status code
            if status_code < 400:
                log_fn = logger.info
            elif status_code < 500:
                log_fn = logger.warning
            else:
                log_fn = logger.error

            log_fn(
                "method=%s path=%s status=%d latency_ms=%.1f key=%s",
                method,
                path,
                status_code,
                latency_ms,
                key_preview,
            )
