# syntax=docker/dockerfile:1

ARG PYTHON_IMAGE=python:3.14.10-slim-trixie@sha256:22eafb370920ad8b429e0aec3fff433e0669968519f5d60469d83729c138b28b

#
# Build stage: install the runtime dependencies into a virtual environment.
#

FROM ${PYTHON_IMAGE} AS build

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore

WORKDIR /app
COPY pyproject.toml ./

RUN python -c 'import tomllib; print(*tomllib.load(open("pyproject.toml", "rb"))["project"]["dependencies"], sep="\n")' > requirements.txt \
 && python -m venv --without-pip /app/.venv \
 && python -m pip --python /app/.venv/bin/python install -r requirements.txt \
 && python -m pip --python /app/.venv/bin/python check

#
# Runtime stage: no build tooling (pip included), the latest Debian security updates,
# unprivileged user, read-only application files.
#

FROM ${PYTHON_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:${PATH}" \
    UVICORN_HOST=0.0.0.0 \
    UVICORN_PORT=80

RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get upgrade -y \
 && rm -rf /var/lib/apt/lists/* \
 && python -m pip uninstall -y pip \
 && useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin app

WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY api ./api

# Binding to port 80 as non-root relies on Docker's default
# net.ipv4.ip_unprivileged_port_start=0. With host networking (or runtimes without
# that default), set UVICORN_PORT to a port above 1023.
USER app
EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request as u; u.urlopen('http://127.0.0.1:' + os.environ.get('UVICORN_PORT', '80') + '/health', timeout=4)"]

# Host and port come from UVICORN_HOST / UVICORN_PORT.
CMD ["uvicorn", "api.main:app"]
