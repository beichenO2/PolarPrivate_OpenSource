# syntax=docker/dockerfile:1
#
# OSS standalone image: API + embedded Web UI on 127.0.0.1:12790.
# Polarisor ecosystem users: do NOT docker compose up here — use PolarProcess
# and `privportal start` instead.

# ── Stage 1: frontend SPA ────────────────────────────────────────────────────
FROM node:22-alpine AS frontend-build

WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ── Stage 2: backend + SPA ───────────────────────────────────────────────────
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS runtime

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/ ./backend/
COPY --from=frontend-build /build/frontend/dist ./frontend/dist/

WORKDIR /app/backend
RUN uv sync --frozen --no-dev

ENV PRIVPORTAL_API_HOST=127.0.0.1 \
    PRIVPORTAL_API_PORT=12790 \
    PRIVPORTAL_DATABASE_URL=sqlite:////app/data/privportal.db

RUN mkdir -p /app/data

VOLUME ["/app/data"]

EXPOSE 12790

CMD ["sh", "-c", "uv run privportal init-db && exec uv run privportal serve"]
