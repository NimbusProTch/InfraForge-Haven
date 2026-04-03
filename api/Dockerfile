# ----- Build stage -----
FROM python:3.12-slim AS builder

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml ./
# Install dependencies only (no source yet) — use a stub app package for metadata
RUN mkdir -p app && touch app/__init__.py && \
    uv pip install --system --no-cache-dir -e "." && \
    rm -rf app

# ----- Runtime stage -----
FROM python:3.12-slim AS runtime

# git is required by the git-worker for GitOps commits to Gitea
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY . .

# Run as non-root user for security
RUN groupadd -r haven && useradd -r -g haven -u 1000 haven && \
    chown -R haven:haven /app
USER 1000:1000

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
