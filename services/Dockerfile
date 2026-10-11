# syntax=docker/dockerfile:1.7
# One Dockerfile, one target per deployable image (ephemeris, trajectory, jobs,
# worker). Dependency stages come first and are shared by every target, so the
# scientific stack installs once per build instead of once per service. Each
# target still copies only its own service package; services stay independent
# images. Build a single one with: docker build -f services/Dockerfile --target trajectory .
#
# Containers run read-only, so .pyc files are written at build time. compileall
# only compiles files without an up-to-date .pyc, so each stage compiles just what
# it added. (uv's --compile-bytecode recompiles the whole environment on every
# install, which redid numpy/scipy in every stage and bloated every layer.)

FROM python:3.12-slim AS base
COPY --from=ghcr.io/astral-sh/uv:0.13.0@sha256:cdc6093146eb3ff6a40107b38f008b789e050e77ad87865e381d9917da55a168 /uv /usr/local/bin/uv
ENV UV_SYSTEM_PYTHON=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.lock ./
# The uv cache mount survives between builds: a lock change re-downloads only what changed.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install -c requirements.lock fastapi uvicorn websockets httpx numpy scipy astropy redis boto3 \
    && python -m compileall -q -j 0 /usr/local/lib/python3.12/site-packages

FROM base AS numerics
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install -c requirements.lock numba \
    && python -m compileall -q -j 0 /usr/local/lib/python3.12/site-packages
ENV NUMBA_CACHE_DIR=/tmp/numba

FROM base AS jobs-deps
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install -c requirements.lock arq sqlalchemy "psycopg[binary]" \
    && python -m compileall -q -j 0 /usr/local/lib/python3.12/site-packages

FROM numerics AS worker-deps
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install -c requirements.lock arq sqlalchemy "psycopg[binary]" \
    && python -m compileall -q -j 0 /usr/local/lib/python3.12/site-packages

FROM base AS ephemeris
COPY packages/tars_core packages/tars_core
COPY packages/tars_contracts packages/tars_contracts
COPY services/ephemeris service
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --no-deps ./packages/tars_core ./packages/tars_contracts ./service \
    && python -m compileall -q -j 0 /usr/local/lib/python3.12/site-packages
USER 10001
EXPOSE 8000
CMD ["uvicorn","ephemeris_service.app:create_app","--factory","--host","0.0.0.0","--port","8000"]

FROM numerics AS trajectory
COPY packages/tars_core packages/tars_core
COPY packages/tars_contracts packages/tars_contracts
COPY services/trajectory service
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --no-deps ./packages/tars_core ./packages/tars_contracts ./service \
    && python -m compileall -q -j 0 /usr/local/lib/python3.12/site-packages
USER 10001
EXPOSE 8000
CMD ["uvicorn","trajectory_service.app:create_app","--factory","--host","0.0.0.0","--port","8000"]

FROM jobs-deps AS jobs
COPY packages/tars_core packages/tars_core
COPY packages/tars_contracts packages/tars_contracts
COPY services/jobs service
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --no-deps ./packages/tars_core ./packages/tars_contracts ./service \
    && python -m compileall -q -j 0 /usr/local/lib/python3.12/site-packages
USER 10001
EXPOSE 8000
CMD ["uvicorn","jobs_service.app:create_app","--factory","--host","0.0.0.0","--port","8000"]

FROM worker-deps AS worker
COPY packages/tars_core packages/tars_core
COPY packages/tars_contracts packages/tars_contracts
COPY services/jobs service
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --no-deps ./packages/tars_core ./packages/tars_contracts ./service \
    && python -m compileall -q -j 0 /usr/local/lib/python3.12/site-packages
USER 10001
CMD ["arq","jobs_service.worker.WorkerSettings"]
