# syntax=docker/dockerfile:1.7
FROM python:3.12-slim

ARG USERNAME=flair
ARG USER_UID=1000
ARG USER_GID=1000
ARG UV_VERSION=0.6.14

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
ENV TZ=UTC
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PATH=/home/${USERNAME}/.local/bin:${PATH}

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Install minimal system dependencies
# hadolint ignore=DL3008
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        tini && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd --gid "${USER_GID}" "${USERNAME}" && \
    useradd --uid "${USER_UID}" --gid "${USER_GID}" --create-home --shell /bin/bash "${USERNAME}"

# Install uv
RUN pip install --no-cache-dir "uv==${UV_VERSION}"

# Copy dependency files
COPY pyproject.toml uv.lock /app/
WORKDIR /app

# Install project dependencies (no dev deps, no editable)
RUN uv sync --frozen --no-dev --no-editable

# Copy worker source
COPY worker/ /app/worker/

# Prepare work directory layout (actual data is mounted at runtime)
RUN mkdir -p /work/input /work/output /work/logs /work/tmp && \
    chown -R "${USERNAME}:${USER_GID}" /work /app

USER ${USERNAME}

# Work directory is the runtime root for mounts
WORKDIR /work

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/app/.venv/bin/python", "-m", "worker.main", "--help"]
