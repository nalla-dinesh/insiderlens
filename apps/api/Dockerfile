# InsiderLens API — production-grade image (Phase 08).
# Multi-stage: builder compiles wheels; final is slim + non-root.
# Build context = REPO ROOT (docker compose passes context: ..), so every
# COPY path below is prefixed apps/api/... deliberately.
# Target: free 512 MB host (Render free tier) — one worker default.
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /build
COPY apps/api/pyproject.toml ./
COPY apps/api/app ./app
RUN pip wheel --no-cache-dir --wheel-dir /wheels .

FROM python:3.11-slim AS final

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PATH="/usr/local/bin:$PATH" \
    # sane production defaults (can be overridden by compose/env)
    ENV=production \
    WEB_CONCURRENCY=1 \
    RUN_MIGRATIONS=0

# non-root user (P-note: free tier runs read-only-ish images; uid 10001)
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app --create-home app

WORKDIR /app
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/*
COPY apps/api/app ./app
COPY apps/api/alembic ./alembic
COPY apps/api/alembic.ini ./alembic.ini
COPY infra/config/rules.yaml /app/config/rules.yaml
COPY apps/api/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh && chown -R app:app /app

USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"

ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
