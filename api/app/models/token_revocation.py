"""Token revocation list — Sprint H2 P9 / H2 #24.

When a tenant member is removed (via `members.py::remove_member`) we need
the deleted user's outstanding JWTs to stop working immediately. The H0
audit found this gap explicitly:

> "Member silindiğinde token revoke edilmiyor — 8 saate kadar erişim
>  devam eder."

Pre-fix the only "revocation" was waiting for the JWT to naturally
expire (~1 hour access token + 8 hour SSO session). For an admin-removed
member, that's an unacceptable window.

## Design

Per-user revocation watermark, not per-token:

  - Each row is `(user_id, force_reauth_after, reason)`
  - When a user is removed from a tenant, we INSERT/UPDATE this row
    with `force_reauth_after = NOW()`
  - On every authenticated request, the JWT verifier checks: is
    `token.iat >= row.force_reauth_after`? If not → 401 forced re-login.
  - User re-authenticates → fresh JWT with `iat > NOW()` → check passes
  - The fresh JWT is reissued with current memberships, so the
    cross-tenant impact of a single tenant removal is correct.

## Cleanup

Rows older than the JWT maximum lifetime (8 hours by default — Keycloak
SSO session max) can be safely deleted by a background task. After that
point any token issued before the revocation has naturally expired.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class TokenRevocation(Base, TimestampMixin):
    """A user-scoped revocation watermark.

    `force_reauth_after` is the timestamp the user MUST have re-issued
    their token after to be considered valid. JWT verification compares
    the token's `iat` claim against this row.
    """

    __tablename__ = "token_revocations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    # Keycloak `sub` claim — the canonical user identifier
    user_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)

    # Any token whose `iat` (issued-at) is BEFORE this timestamp is rejected.
    force_reauth_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    # Free-form audit string (e.g. "removed from tenant rotterdam by admin user-X")
    reason: Mapped[str | None] = mapped_column(String(512), nullable=True)

    __table_args__ = (Index("ix_token_revocations_force_reauth_after_v2", "force_reauth_after"),)
