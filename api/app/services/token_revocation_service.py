"""Token revocation service — Sprint H2 P9 / H2 #24.

Manages the `token_revocations` table:

  - `revoke_user(user_id, reason)` — bumps the user's reauth watermark
    to NOW(). Called when a tenant member is removed.
  - `is_token_revoked(user_id, token_iat)` — returns True if the token
    must be rejected. Called by the JWT verifier on every request.
  - `cleanup_expired()` — deletes watermarks older than 8 hours
    (max JWT lifetime). Called by a background task.

## Caching

The check is on the hot path of every authenticated request, so it
needs to be fast. We use a per-process in-memory cache with a 60-second
TTL: `_revocation_cache: dict[user_id, (force_reauth_after, fetched_at)]`.

The 60s TTL means: a fresh revocation has up to a 60s grace period
where the deleted member can still hit the API. That's a tradeoff
against making every request a DB lookup. For a multi-tenant SaaS
admin-remove flow, 60s is well within "immediate" expectations.

For zero-grace revocation, set `_REVOCATION_CACHE_TTL = 0` (DB lookup
every request). The current dev cluster sees ~hundreds of requests/sec
which would be fine but production might want to lift this.
"""

import logging
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.token_revocation import TokenRevocation

logger = logging.getLogger(__name__)

# In-process cache: user_id -> (force_reauth_after_epoch, fetched_at_monotonic)
_revocation_cache: dict[str, tuple[float, float]] = {}
_REVOCATION_CACHE_TTL_SECONDS = 60.0

# How long after the watermark we keep the row before cleanup. Should be
# at least the JWT max lifetime (Keycloak SSO Session Max = 8h by default).
_REVOCATION_RETENTION_HOURS = 24


async def revoke_user(
    db: AsyncSession,
    user_id: str,
    reason: str | None = None,
) -> None:
    """Bump the user's reauth watermark to NOW().

    Idempotent — if a row exists for the user, the watermark is updated.
    Used by `members.py::remove_member` and similar admin-driven removal
    flows.

    The user's currently-issued JWTs (issued before NOW()) will start
    failing on the next request. The user can re-authenticate normally
    and will get a fresh JWT with `iat > force_reauth_after`.
    """
    now = datetime.now(UTC)
    existing_q = await db.execute(select(TokenRevocation).where(TokenRevocation.user_id == user_id))
    existing = existing_q.scalar_one_or_none()

    if existing is None:
        row = TokenRevocation(
            user_id=user_id,
            force_reauth_after=now,
            reason=reason,
        )
        db.add(row)
    else:
        existing.force_reauth_after = now
        existing.reason = reason

    await db.flush()
    # Invalidate the in-memory cache so the next check sees the new value.
    _revocation_cache.pop(user_id, None)
    logger.info("Token revoked for user_id=%s reason=%r", user_id, reason)


async def is_token_revoked(
    db: AsyncSession,
    user_id: str,
    token_iat_epoch: int | float | None,
) -> bool:
    """Return True if the JWT must be rejected.

    `token_iat_epoch` is the JWT's `iat` claim (issued-at, as a Unix
    timestamp). If the token has no `iat` claim or it's None, we treat
    that as a malformed token — return True (reject).
    """
    if token_iat_epoch is None:
        return True

    # In-memory cache lookup
    cached = _revocation_cache.get(user_id)
    now_mono = time.monotonic()
    if cached is not None:
        force_reauth_after_epoch, fetched_at = cached
        if (now_mono - fetched_at) < _REVOCATION_CACHE_TTL_SECONDS:
            return float(token_iat_epoch) < force_reauth_after_epoch

    # Cache miss / stale — DB lookup
    result = await db.execute(select(TokenRevocation.force_reauth_after).where(TokenRevocation.user_id == user_id))
    row = result.scalar_one_or_none()
    if row is None:
        # No revocation row → cache "not revoked" as epoch 0 so subsequent
        # cache hits return False fast.
        _revocation_cache[user_id] = (0.0, now_mono)
        return False

    # SQLite drops tzinfo on round-trip. Postgres preserves it. Normalise:
    # if the value is naive, assume it's UTC (which is what we wrote).
    # Otherwise `.timestamp()` would interpret it as local time and the
    # epoch comparison would be off by the local TZ offset.
    if isinstance(row, datetime) and row.tzinfo is None:
        row_aware = row.replace(tzinfo=UTC)
    elif isinstance(row, datetime):
        row_aware = row
    else:
        # Defensive — should never happen for a DateTime column
        return False

    force_reauth_after_epoch = row_aware.timestamp()
    _revocation_cache[user_id] = (force_reauth_after_epoch, now_mono)
    return float(token_iat_epoch) < force_reauth_after_epoch


async def cleanup_expired_revocations(db: AsyncSession) -> int:
    """Delete revocation rows older than `_REVOCATION_RETENTION_HOURS`.

    After that point, any token issued before the revocation has
    naturally expired (Keycloak SSO Session Max default = 8h, retention
    = 24h gives a safe margin).

    Returns the number of rows deleted.
    """
    cutoff = datetime.now(UTC) - timedelta(hours=_REVOCATION_RETENTION_HOURS)
    result = await db.execute(delete(TokenRevocation).where(TokenRevocation.force_reauth_after < cutoff))
    await db.flush()
    deleted = result.rowcount or 0
    if deleted > 0:
        logger.info("Cleaned up %d expired token revocation rows", deleted)
    return deleted


def _clear_cache_for_tests() -> None:
    """Test-only — clear the in-process cache between tests."""
    _revocation_cache.clear()
