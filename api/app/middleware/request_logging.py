"""Request logging middleware with correlation ID.

Adds X-Request-ID header to all requests/responses and logs
method, path, status code, and latency for observability.
"""

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("haven.access")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log every HTTP request with timing and correlation ID."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        start = time.monotonic()

        response = await call_next(request)

        latency_ms = round((time.monotonic() - start) * 1000, 1)
        response.headers["X-Request-ID"] = request_id

        # Skip noisy health check logs
        path = request.url.path
        if path not in ("/health", "/readiness"):
            logger.info(
                "%s %s %d %.1fms [%s]",
                request.method,
                path,
                response.status_code,
                latency_ms,
                request_id,
            )

        return response
