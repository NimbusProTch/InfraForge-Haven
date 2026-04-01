"""Post-provision database setup: custom user, database, and tenant-namespace secret.

After Everest creates a PostgreSQL/MySQL/MongoDB instance with admin credentials,
this module connects with those admin creds and creates:
  1. A custom database (if requested)
  2. A custom user with password
  3. A K8s Secret in the tenant namespace with the custom credentials

This solves the cross-namespace secret problem: Everest stores admin secrets in the
`everest` namespace, but app pods run in `tenant-*` namespaces. By creating a new
secret in the tenant namespace, apps can reference it via `envFrom.secretRef`.
"""

import base64
import logging
import re
import secrets
import string

import asyncpg
from kubernetes.client import ApiException, V1ObjectMeta, V1Secret

from app.k8s.client import K8sClient

# Lazy imports for optional DB drivers (aiomysql, motor)
# Imported inside functions to avoid hard dependency when not needed

_SAFE_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")

logger = logging.getLogger(__name__)

EVEREST_NAMESPACE = "everest"


def generate_password(length: int = 24) -> str:
    """Generate a secure random password (alphanumeric, no special chars for URL safety)."""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


async def read_admin_credentials(
    k8s: K8sClient, secret_name: str, namespace: str = EVEREST_NAMESPACE,
) -> dict[str, str]:
    """Read admin credentials from an Everest-managed K8s secret."""
    if not k8s.is_available() or k8s.core_v1 is None:
        raise RuntimeError("K8s client not available")

    secret = k8s.core_v1.read_namespaced_secret(name=secret_name, namespace=namespace)
    creds: dict[str, str] = {}
    for key, val in (secret.data or {}).items():
        creds[key] = base64.b64decode(val).decode()
    return creds


async def create_custom_database(
    k8s: K8sClient,
    everest_secret_name: str,
    db_name: str | None = None,
    db_user: str | None = None,
    db_password: str | None = None,
) -> dict[str, str]:
    """Connect to Everest PG with admin creds, create custom database + user.

    Args:
        k8s: Kubernetes client for reading admin secret.
        everest_secret_name: Name of the Everest admin secret in everest namespace.
        db_name: Custom database name. If None, uses default 'postgres'.
        db_user: Custom username. If None, uses db_name or 'app'.
        db_password: Custom password. If None, auto-generated.

    Returns:
        Dict with: host, port, user, password, database, database_url
    """
    admin_creds = await read_admin_credentials(k8s, everest_secret_name)

    admin_host = admin_creds.get("host", "")
    admin_port = int(admin_creds.get("port", "5432"))
    admin_user = admin_creds.get("user", "postgres")
    admin_password = admin_creds.get("password", "")

    # Keep primary endpoint for admin operations (DDL, user creation).
    # Primary connects directly to PostgreSQL (no PgBouncer), so custom users work.
    # The returned credentials use the HA endpoint for app connections.

    if not db_user:
        db_user = db_name or "app"
    if not db_password:
        db_password = generate_password()

    # Validate identifiers to prevent SQL injection.
    # DDL statements (CREATE DATABASE/USER) don't support parameterized queries,
    # so we enforce a strict allowlist pattern instead.
    for name, label in [(db_name, "db_name"), (db_user, "db_user")]:
        if name and not _SAFE_IDENTIFIER.match(name):
            raise ValueError(f"Invalid {label}: must match ^[a-z][a-z0-9_]*$ (got '{name}')")

    conn = await asyncpg.connect(
        host=admin_host,
        port=admin_port,
        user=admin_user,
        password=admin_password,
        database="postgres",
    )

    try:
        # Create database if requested
        if db_name:
            exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", db_name)
            if not exists:
                # Safe: db_name validated against _SAFE_IDENTIFIER
                await conn.execute(f'CREATE DATABASE "{db_name}"')
                logger.info("Created database: %s", db_name)

        # Create user if not exists
        # DDL doesn't support $1 params in asyncpg, but db_user is validated by _SAFE_IDENTIFIER
        # and db_password is either auto-generated (alphanumeric) or escaped here
        safe_password = db_password.replace("'", "''")
        user_exists = await conn.fetchval("SELECT 1 FROM pg_roles WHERE rolname = $1", db_user)
        if not user_exists:
            await conn.execute(f"CREATE USER \"{db_user}\" WITH PASSWORD '{safe_password}'")
            logger.info("Created user: %s", db_user)
        else:
            await conn.execute(f"ALTER USER \"{db_user}\" WITH PASSWORD '{safe_password}'")
            logger.info("Updated password for existing user: %s", db_user)

        # Grant privileges
        target_db = db_name or "postgres"
        await conn.execute(f'GRANT ALL PRIVILEGES ON DATABASE "{target_db}" TO "{db_user}"')

        # Grant schema privileges (for Alembic migrations)
        if db_name:
            db_conn = await asyncpg.connect(
                host=admin_host, port=admin_port,
                user=admin_user, password=admin_password,
                database=db_name,
            )
            try:
                await db_conn.execute(f'GRANT ALL ON SCHEMA public TO "{db_user}"')
                await db_conn.execute(
                    f'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO "{db_user}"'
                )
                await db_conn.execute(
                    f'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO "{db_user}"'
                )
            finally:
                await db_conn.close()

    finally:
        await conn.close()

    # For app connections, prefer HA endpoint (ClusterIP, stable) over primary (headless).
    # Primary is used only for admin DDL operations above.
    app_host = admin_host
    if "-primary." in admin_host:
        app_host = admin_host.replace("-primary.", "-ha.")

    from urllib.parse import quote as urlquote

    database_url = f"postgresql://{db_user}:{urlquote(db_password, safe='')}@{app_host}:{admin_port}/{db_name or 'postgres'}"

    return {
        "DATABASE_URL": database_url,
        "DB_HOST": app_host,
        "DB_PORT": str(admin_port),
        "DB_USER": db_user,
        "DB_PASSWORD": db_password,
        "DB_NAME": db_name or "postgres",
    }


async def create_custom_mysql_database(
    k8s: K8sClient,
    everest_secret_name: str,
    db_name: str | None = None,
    db_user: str | None = None,
    db_password: str | None = None,
) -> dict[str, str]:
    """Connect to Everest MySQL with admin creds, create custom database + user.

    Same pattern as create_custom_database (PostgreSQL) but uses aiomysql.
    """
    import aiomysql

    admin_creds = await read_admin_credentials(k8s, everest_secret_name)

    admin_host = admin_creds.get("host", "")
    admin_port = int(admin_creds.get("port", "3306"))
    admin_user = admin_creds.get("user", "root")
    admin_password = admin_creds.get("password", "")

    if not db_user:
        db_user = db_name or "app"
    if not db_password:
        db_password = generate_password()

    # Validate identifiers to prevent SQL injection (DDL doesn't support params)
    for name, label in [(db_name, "db_name"), (db_user, "db_user")]:
        if name and not _SAFE_IDENTIFIER.match(name):
            raise ValueError(f"Invalid {label}: must match ^[a-z][a-z0-9_]*$ (got '{name}')")

    conn = await aiomysql.connect(
        host=admin_host,
        port=admin_port,
        user=admin_user,
        password=admin_password,
    )

    try:
        async with conn.cursor() as cur:
            if db_name:
                await cur.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}`")
                logger.info("Created MySQL database: %s", db_name)

            # CREATE USER IF NOT EXISTS doesn't update password, so ALTER afterwards
            # Use parameterized queries for password to prevent SQL injection
            await cur.execute("CREATE USER IF NOT EXISTS %s@'%%' IDENTIFIED BY %s", (db_user, db_password))
            await cur.execute("ALTER USER %s@'%%' IDENTIFIED BY %s", (db_user, db_password))

            target_db = db_name or "mysql"
            # db_user validated by _SAFE_IDENTIFIER, target_db validated or is literal "mysql"
            await cur.execute(f"GRANT ALL PRIVILEGES ON `{target_db}`.* TO '{db_user}'@'%%'")
            await cur.execute("FLUSH PRIVILEGES")
            logger.info("Created/updated MySQL user: %s with access to %s", db_user, target_db)
    finally:
        conn.close()

    database_url = f"mysql://{db_user}:{db_password}@{admin_host}:{admin_port}/{db_name or 'mysql'}"

    return {
        "DATABASE_URL": database_url,
        "DB_HOST": admin_host,
        "DB_PORT": str(admin_port),
        "DB_USER": db_user,
        "DB_PASSWORD": db_password,
        "DB_NAME": db_name or "mysql",
    }


async def create_custom_mongodb_database(
    k8s: K8sClient,
    everest_secret_name: str,
    db_name: str | None = None,
    db_user: str | None = None,
    db_password: str | None = None,
) -> dict[str, str]:
    """Connect to Everest MongoDB with admin creds, create custom database + user.

    Same pattern as create_custom_database (PostgreSQL) but uses motor (async pymongo).
    """
    import motor.motor_asyncio

    admin_creds = await read_admin_credentials(k8s, everest_secret_name)

    admin_host = admin_creds.get("host", "")
    admin_port = int(admin_creds.get("port", "27017"))
    admin_user = admin_creds.get("user", "")
    admin_password = admin_creds.get("password", "")

    if not db_user:
        db_user = db_name or "app"
    if not db_password:
        db_password = generate_password()

    # Validate identifiers
    for name, label in [(db_name, "db_name"), (db_user, "db_user")]:
        if name and not _SAFE_IDENTIFIER.match(name):
            raise ValueError(f"Invalid {label}: must match ^[a-z][a-z0-9_]*$ (got '{name}')")

    target_db = db_name or "app"

    # Use constructor params to avoid URL-encoding issues with special chars in admin password
    client = motor.motor_asyncio.AsyncIOMotorClient(
        host=admin_host,
        port=admin_port,
        username=admin_user,
        password=admin_password,
        authSource="admin",
        serverSelectionTimeoutMS=10000,
    )

    try:
        db = client[target_db]

        # Check if user exists in this database
        existing = await db.command("usersInfo", db_user)
        if existing.get("users"):
            await db.command("updateUser", db_user, pwd=db_password)
            logger.info("Updated MongoDB user: %s on db %s", db_user, target_db)
        else:
            await db.command(
                "createUser",
                db_user,
                pwd=db_password,
                roles=[{"role": "readWrite", "db": target_db}],
            )
            logger.info("Created MongoDB user: %s on db %s", db_user, target_db)
    finally:
        client.close()

    database_url = f"mongodb://{db_user}:{db_password}@{admin_host}:{admin_port}/{target_db}?authSource={target_db}"

    return {
        "DATABASE_URL": database_url,
        "DB_HOST": admin_host,
        "DB_PORT": str(admin_port),
        "DB_USER": db_user,
        "DB_PASSWORD": db_password,
        "DB_NAME": target_db,
    }


async def create_tenant_secret(
    k8s: K8sClient,
    tenant_namespace: str,
    secret_name: str,
    credentials: dict[str, str],
) -> None:
    """Create or update a K8s Secret in the tenant namespace."""
    if not k8s.is_available() or k8s.core_v1 is None:
        raise RuntimeError("K8s client not available")

    encoded_data = {k: base64.b64encode(v.encode()).decode() for k, v in credentials.items()}

    secret = V1Secret(
        api_version="v1",
        kind="Secret",
        metadata=V1ObjectMeta(
            name=secret_name,
            namespace=tenant_namespace,
            labels={"haven.io/managed": "true", "haven.io/type": "service-credentials"},
        ),
        data=encoded_data,
        type="Opaque",
    )

    try:
        k8s.core_v1.create_namespaced_secret(tenant_namespace, secret)
        logger.info("Created secret %s/%s", tenant_namespace, secret_name)
    except ApiException as e:
        if e.status == 409:
            # Already exists — update
            k8s.core_v1.replace_namespaced_secret(secret_name, tenant_namespace, secret)
            logger.info("Updated secret %s/%s", tenant_namespace, secret_name)
        else:
            raise


async def delete_tenant_secret(k8s: K8sClient, tenant_namespace: str, secret_name: str) -> None:
    """Delete a service credentials secret from the tenant namespace."""
    if not k8s.is_available() or k8s.core_v1 is None:
        return
    try:
        k8s.core_v1.delete_namespaced_secret(secret_name, tenant_namespace)
        logger.info("Deleted secret %s/%s", tenant_namespace, secret_name)
    except ApiException as e:
        if e.status != 404:
            raise


def tenant_secret_name(service_name: str) -> str:
    """Standardized secret name for a service in tenant namespace."""
    return f"svc-{service_name}"
