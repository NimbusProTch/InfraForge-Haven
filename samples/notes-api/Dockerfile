# Multi-stage build for notes-api sample (iyziops)
FROM python:3.12-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim
# Non-root runtime (PSA restricted compatible)
RUN useradd -u 10001 -m -s /bin/bash app
WORKDIR /app
COPY --from=builder /install /usr/local
COPY app.py .
USER 10001
EXPOSE 8000
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health',timeout=2).getcode()==200 else 1)"
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
