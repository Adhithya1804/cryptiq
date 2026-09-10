# syntax=docker/dockerfile:1.7

########################################################################
# Stage 1 — builder: install the pinned dependency set into a venv.
########################################################################
FROM python:3.12-slim-bookworm AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build

# Create an isolated virtualenv we can copy wholesale into the runtime stage.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Dependencies first so the layer caches until requirements.txt changes.
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# Project source (no VCS, no tests, no .env — see .dockerignore).
COPY pyproject.toml README.md alembic.ini ./
COPY app ./app
COPY migrations ./migrations

# Install the app itself (console scripts: cryptiq-api, cryptiq) without deps.
RUN pip install --no-deps .

########################################################################
# Stage 2 — runtime: slim image, non-root, no build tooling.
########################################################################
FROM python:3.12-slim-bookworm AS runtime

# tini gives us correct signal forwarding / zombie reaping as PID 1.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends tini; \
    rm -rf /var/lib/apt/lists/*

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    DATABASE_URL=sqlite:////data/cryptiq.db \
    RUN_WORKER=true

# Non-root runtime user; owns the writable data dir so a fresh named volume
# inherits writable permissions.
RUN set -eux; \
    groupadd --system --gid 1001 cryptiq; \
    useradd --system --uid 1001 --gid 1001 --home /app --shell /usr/sbin/nologin cryptiq; \
    mkdir -p /app /data; \
    chown -R cryptiq:cryptiq /app /data

COPY --from=builder --chown=root:root /opt/venv /opt/venv

WORKDIR /app
COPY --chown=cryptiq:cryptiq alembic.ini ./
COPY --chown=cryptiq:cryptiq app ./app
COPY --chown=cryptiq:cryptiq migrations ./migrations
COPY --chown=cryptiq:cryptiq docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

USER cryptiq

VOLUME ["/data"]
EXPOSE 8000

# Readiness: process up AND database reachable.
HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=4).status==200 else 1)" || exit 1

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]
