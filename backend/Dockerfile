FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Build-context knobs (both default to the plain open build; nothing to pass).
#
# BASE_DIR    — this `backend/` directory, relative to the build context. The open
#               build uses the default (context = `backend/`). A distribution that
#               also needs files from outside this repo builds from a wider context
#               and passes e.g. BASE_DIR=vicoa/backend.
# OVERLAY_SRC — an extra Python source root copied to /app/overlay-src and placed on
#               PYTHONPATH. Defaults to an empty directory in this repo, so the open
#               image gets nothing extra and the optional-overlay import in
#               backend/main.py (`find_spec("cloud")`) resolves to None.
ARG BASE_DIR=.
ARG OVERLAY_SRC=docker/empty-overlay

# Install build tooling required by several dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Pre-copy requirement files to preserve layer caching
COPY ${BASE_DIR}/src/shared/requirements.txt /app/src/shared/requirements.txt
COPY ${BASE_DIR}/src/backend/requirements.txt /app/src/backend/requirements.txt
COPY ${BASE_DIR}/src/servers/requirements.txt /app/src/servers/requirements.txt
COPY ${BASE_DIR}/requirements-dev.txt /app/requirements-dev.txt
COPY ${BASE_DIR}/pyproject.toml /app/pyproject.toml

# Install Python dependencies (backend/servers pull in shared via -r)
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /app/src/backend/requirements.txt \
    && pip install --no-cache-dir -r /app/src/servers/requirements.txt

# Copy application source and operational scripts
COPY ${BASE_DIR}/src/protocol /app/src/protocol
COPY ${BASE_DIR}/src/shared /app/src/shared
COPY ${BASE_DIR}/src/backend /app/src/backend
COPY ${BASE_DIR}/src/servers /app/src/servers
COPY ${BASE_DIR}/src/integrations /app/src/integrations
COPY ${BASE_DIR}/scripts /app/scripts

# Optional extra source root (empty in the open build)
COPY ${OVERLAY_SRC}/ /app/overlay-src/

# Ensure shell helpers are executable for release commands
RUN chmod +x /app/scripts/*.sh

# Configure runtime environment for Fly processes
ENV PYTHONPATH=/app/src:/app/overlay-src
ENV API_PORT=8000
ENV MCP_SERVER_PORT=8080
ENV ENVIRONMENT=production

# Expose ports for both backend and MCP server
EXPOSE 8000 8080

# No default CMD - Fly.io uses processes defined in fly.toml
