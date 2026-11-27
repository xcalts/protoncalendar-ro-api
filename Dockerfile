# syntax=docker/dockerfile:1

ARG PYTHON_IMAGE=python:3.14.10-slim-trixie@sha256:9aaa474097d094040649f2162a627c0049b408f52138d980916788d80f04802f

#
# Build stage: install the runtime dependencies into a virtual environment.
#

FROM ${PYTHON_IMAGE} AS build

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore

WORKDIR /app
COPY pyproject.toml ./
# Install the [project] dependencies of pyproject.toml, not the project itself (the
# application code is copied as-is below). pip cannot install only the dependencies
# of a project, so they are read with tomllib. The development tools
# ([dependency-groups] dev) never enter the image. "pip check" fails the build if
# the installed packages are inconsistent.
RUN python -c 'import tomllib; print(*tomllib.load(open("pyproject.toml", "rb"))["project"]["dependencies"], sep="\n")' > requirements.txt \
 && python -m venv /app/.venv \
 && /app/.venv/bin/pip install -r requirements.txt \
 && /app/.venv/bin/pip check

#
# Runtime stage: no build tooling, unprivileged user, read-only application files.
#

FROM ${PYTHON_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:${PATH}" \
    UVICORN_HOST=0.0.0.0 \
    UVICORN_PORT=80

RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin app

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
