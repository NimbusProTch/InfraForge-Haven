"""Per-endpoint rate limiting configuration.

Sprint 4: Sensitive endpoints get stricter rate limits than the global default.
Uses slowapi/Limiter. Import `limiter` in router files and apply as a decorator.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])

# Rate limit constants for sensitive endpoints
RATE_AUTH = "20/minute"
RATE_BUILD = "10/minute"
RATE_SERVICE_PROVISION = "5/minute"
RATE_WEBHOOK = "60/minute"
RATE_TENANT_CREATE = "3/minute"
# Public access-request form — anonymous writers, keep tight.
RATE_ACCESS_REQUEST = "5/hour"
