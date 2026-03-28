import asyncio
import os
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Alembic Config object
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override sqlalchemy.url from DATABASE_URL env var if set
if os.environ.get("DATABASE_URL"):
    config.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])

# Import all models so Alembic can detect them
from app.models.application import Application  # noqa: E402, F401
from app.models.audit_log import AuditLog  # noqa: E402, F401
from app.models.base import Base  # noqa: E402
from app.models.cluster import Cluster  # noqa: E402, F401
from app.models.cronjob import CronJob  # noqa: E402, F401
from app.models.data_retention_policy import DataRetentionPolicy  # noqa: E402, F401
from app.models.deployment import BuildJob, Deployment  # noqa: E402, F401
from app.models.domain import DomainVerification  # noqa: E402, F401
from app.models.environment import Environment  # noqa: E402, F401
from app.models.managed_service import ManagedService  # noqa: E402, F401
from app.models.organization import Organization, OrganizationMember, OrgTenantMembership, SSOConfig  # noqa: E402, F401
from app.models.tenant import Tenant  # noqa: E402, F401
from app.models.tenant_member import TenantMember  # noqa: E402, F401
from app.models.usage_record import UsageRecord  # noqa: E402, F401
from app.models.user_consent import UserConsent  # noqa: E402, F401

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
