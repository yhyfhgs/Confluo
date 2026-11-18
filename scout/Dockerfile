# syntax=docker/dockerfile:1.7
# Confluo Scout image: the web UI is built with Node, the service runs on Python 3.13 (CPU torch).

FROM node:24-slim AS web
WORKDIR /web
RUN corepack enable
COPY web/package.json web/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY web/ ./
RUN pnpm build

FROM python:3.13-slim AS app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
COPY --from=ghcr.io/astral-sh/uv:0.12.8 /uv /usr/local/bin/uv
WORKDIR /app/server
COPY server/pyproject.toml server/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project
COPY server/src ./src
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev
COPY registry /app/registry
COPY --from=web /web/dist /app/web/dist
ENV PATH="/app/server/.venv/bin:${PATH}"
EXPOSE 8000
CMD ["uvicorn", "confluo_scout.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--timeout-graceful-shutdown", "20"]
