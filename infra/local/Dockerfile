# syntax=docker/dockerfile:1.7
# Multi-arch (linux/arm64 + linux/amd64), multi-stage Dockerfile.
#
# Stages:
#   backend-base    — python 3.14-slim with installed deps (cached layer)
#   backend-dev     — bind-mount-friendly (uvicorn --reload), used by compose.dev
#   backend-prod    — copies src in, gunicorn w/ uvicorn workers
#   frontend-base   — node:22-alpine with npm deps installed (cached layer)
#   frontend-dev    — vite dev server, bind-mount-friendly
#   frontend-prod   — built dist served by nginx
#
# Build:
#   docker buildx build --platform linux/amd64,linux/arm64 \
#     --target backend-prod -t ghcr.io/.../app:0.1.0 .

# ─── BACKEND ──────────────────────────────────────────────────────────────────

FROM python:3.14-slim AS backend-base
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      curl ca-certificates build-essential libpq-dev \
 && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt
# Install gunicorn for prod (not in requirements.txt so dev users skip it)
RUN pip install "gunicorn>=22.0"

FROM backend-base AS backend-dev
# Source mounted at /app/src + /app/alembic via compose volumes; nothing copied here.
# uvicorn --reload watches /app/src by default (cwd).
EXPOSE 8000
CMD ["uvicorn", "src.api.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--reload", "--reload-dir", "src"]

FROM backend-base AS backend-prod
# OpenShift-friendly: random non-root UID; group 0 owns /app for write paths.
ARG APP_UID=10001
RUN groupadd -r app && useradd -r -u ${APP_UID} -g app -d /app -s /sbin/nologin app \
 && chown -R app:0 /app && chmod -R g=u /app
COPY --chown=app:0 backend/src ./src
COPY --chown=app:0 backend/alembic ./alembic
COPY --chown=app:0 backend/alembic.ini ./alembic.ini
USER ${APP_UID}
EXPOSE 8000
# Web entrypoint (worker overrides via CMD in deployment).
# 4 workers per pod is a sane default; HPA scales pods, not in-pod workers.
CMD ["gunicorn", "src.api.main:app", \
     "-k", "uvicorn.workers.UvicornWorker", \
     "-w", "4", "-b", "0.0.0.0:8000", \
     "--access-logfile", "-", "--error-logfile", "-", \
     "--graceful-timeout", "30"]

# ─── FRONTEND ─────────────────────────────────────────────────────────────────

FROM node:22-alpine AS frontend-base
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund

FROM frontend-base AS frontend-dev
# Source mounted at /app/src via compose volumes.
COPY frontend/ ./
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]

FROM frontend-base AS frontend-build
COPY frontend/ ./
RUN npm run build

FROM nginx:1.27-alpine AS frontend-prod
COPY --from=frontend-build /app/dist /usr/share/nginx/html
COPY infra/local/nginx.conf /etc/nginx/conf.d/default.conf
# nginx already runs as non-root in alpine image with the standard config.
EXPOSE 8080
