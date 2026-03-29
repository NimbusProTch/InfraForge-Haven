"""Smart dependency detection service.

Analyzes GitHub repository content to detect:
- Language/framework
- Database needs (PostgreSQL, MySQL, MongoDB)
- Cache needs (Redis)
- Queue needs (RabbitMQ)
- Start command
"""

import logging

import httpx

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"

# Detection patterns per file type
_PYTHON_DB_PATTERNS = {
    "sqlalchemy": "postgres",
    "asyncpg": "postgres",
    "psycopg": "postgres",
    "django.db": "postgres",
    "prisma": "postgres",
    "pymysql": "mysql",
    "mysqlclient": "mysql",
    "pymongo": "mongodb",
    "mongoengine": "mongodb",
    "motor": "mongodb",
}

_PYTHON_CACHE_PATTERNS = {
    "redis": "redis",
    "aioredis": "redis",
    "redis-py": "redis",
}

_PYTHON_QUEUE_PATTERNS = {
    "pika": "rabbitmq",
    "aio-pika": "rabbitmq",
    "celery": "rabbitmq",
    "kombu": "rabbitmq",
}

_NODE_DB_PATTERNS = {
    "pg": "postgres",
    "postgres": "postgres",
    "sequelize": "postgres",
    "typeorm": "postgres",
    "prisma": "postgres",
    "mysql2": "mysql",
    "mongoose": "mongodb",
    "mongodb": "mongodb",
}

_NODE_CACHE_PATTERNS = {
    "redis": "redis",
    "ioredis": "redis",
}

_NODE_QUEUE_PATTERNS = {
    "amqplib": "rabbitmq",
    "amqp-connection-manager": "rabbitmq",
}


async def detect_dependencies(owner: str, repo: str, branch: str = "main", github_token: str | None = None) -> dict:
    """Analyze a GitHub repository and detect dependencies.

    Returns:
        {
            "language": "python" | "node" | "go" | "ruby" | "unknown",
            "framework": "fastapi" | "django" | "express" | "nextjs" | etc,
            "databases": ["postgres", "mysql", "mongodb"],
            "caches": ["redis"],
            "queues": ["rabbitmq"],
            "has_dockerfile": bool,
            "suggested_services": [{"type": "postgres", "reason": "SQLAlchemy detected"}],
        }
    """
    headers = {"Accept": "application/vnd.github.v3+json"}
    if github_token:
        headers["Authorization"] = f"token {github_token}"

    result: dict = {
        "language": "unknown",
        "framework": None,
        "databases": [],
        "caches": [],
        "queues": [],
        "has_dockerfile": False,
        "suggested_services": [],
    }

    try:
        async with httpx.AsyncClient() as client:
            # Get repo tree (recursive, shallow)
            tree_resp = await client.get(
                f"{GITHUB_API}/repos/{owner}/{repo}/git/trees/{branch}?recursive=1",
                headers=headers,
                timeout=15.0,
            )
            if not tree_resp.is_success:
                logger.warning("Failed to fetch repo tree: %d", tree_resp.status_code)
                return result

            tree = tree_resp.json().get("tree", [])
            filenames = {item["path"] for item in tree if item["type"] == "blob"}

            # Detect language
            if "requirements.txt" in filenames or "pyproject.toml" in filenames or "setup.py" in filenames:
                result["language"] = "python"
            elif "package.json" in filenames:
                result["language"] = "node"
            elif "go.mod" in filenames:
                result["language"] = "go"
            elif "Gemfile" in filenames:
                result["language"] = "ruby"
            elif "Cargo.toml" in filenames:
                result["language"] = "rust"

            # Check for Dockerfile
            result["has_dockerfile"] = "Dockerfile" in filenames or any(f.endswith("/Dockerfile") for f in filenames)

            # Analyze dependency files for services
            if result["language"] == "python":
                deps_content = await _fetch_file(client, owner, repo, branch, "requirements.txt", headers)
                if not deps_content:
                    deps_content = await _fetch_file(client, owner, repo, branch, "pyproject.toml", headers)
                if deps_content:
                    result = _analyze_python_deps(deps_content, result)

            elif result["language"] == "node":
                pkg_content = await _fetch_file(client, owner, repo, branch, "package.json", headers)
                if pkg_content:
                    result = _analyze_node_deps(pkg_content, result)

    except Exception as exc:  # noqa: BLE001
        logger.warning("Dependency detection failed: %s", exc)

    # Build suggested services list
    for db in result["databases"]:
        result["suggested_services"].append({"type": db, "reason": f"{db} dependency detected"})
    for cache in result["caches"]:
        result["suggested_services"].append({"type": cache, "reason": f"{cache} dependency detected"})
    for queue in result["queues"]:
        result["suggested_services"].append({"type": queue, "reason": f"{queue} dependency detected"})

    return result


async def _fetch_file(
    client: httpx.AsyncClient, owner: str, repo: str, branch: str, path: str, headers: dict
) -> str | None:
    """Fetch raw file content from GitHub."""
    resp = await client.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}?ref={branch}",
        headers={**headers, "Accept": "application/vnd.github.v3.raw"},
        timeout=15.0,
    )
    if resp.is_success:
        return resp.text
    return None


def _analyze_python_deps(content: str, result: dict) -> dict:
    """Detect Python framework and service dependencies."""
    content_lower = content.lower()

    # Framework detection
    if "fastapi" in content_lower:
        result["framework"] = "fastapi"
    elif "django" in content_lower:
        result["framework"] = "django"
    elif "flask" in content_lower:
        result["framework"] = "flask"

    # DB detection
    dbs = set()
    for pattern, db_type in _PYTHON_DB_PATTERNS.items():
        if pattern in content_lower:
            dbs.add(db_type)
    result["databases"] = list(dbs)

    # Cache detection
    caches = set()
    for pattern, cache_type in _PYTHON_CACHE_PATTERNS.items():
        if pattern in content_lower:
            caches.add(cache_type)
    result["caches"] = list(caches)

    # Queue detection
    queues = set()
    for pattern, queue_type in _PYTHON_QUEUE_PATTERNS.items():
        if pattern in content_lower:
            queues.add(queue_type)
    result["queues"] = list(queues)

    return result


def _analyze_node_deps(content: str, result: dict) -> dict:
    """Detect Node.js framework and service dependencies."""
    content_lower = content.lower()

    # Framework detection
    if '"next"' in content_lower or '"next":' in content_lower:
        result["framework"] = "nextjs"
    elif '"express"' in content_lower:
        result["framework"] = "express"
    elif '"nestjs"' in content_lower or '"@nestjs' in content_lower:
        result["framework"] = "nestjs"

    # DB detection
    dbs = set()
    for pattern, db_type in _NODE_DB_PATTERNS.items():
        if f'"{pattern}"' in content_lower:
            dbs.add(db_type)
    result["databases"] = list(dbs)

    # Cache detection
    caches = set()
    for pattern, cache_type in _NODE_CACHE_PATTERNS.items():
        if f'"{pattern}"' in content_lower:
            caches.add(cache_type)
    result["caches"] = list(caches)

    # Queue detection
    queues = set()
    for pattern, queue_type in _NODE_QUEUE_PATTERNS.items():
        if f'"{pattern}"' in content_lower:
            queues.add(queue_type)
    result["queues"] = list(queues)

    return result
