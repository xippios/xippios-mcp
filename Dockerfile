# The xippios-mcp host as a container image: every source package of the extra `all`,
# installed from this checkout with uv.lock (the tested set), served over streamable HTTP.
#
#   docker build -t xippios-mcp .
#   docker run --rm -p 8000:8000 \
#     -v "$PWD/host.toml:/etc/xippios-mcp/host.toml:ro" \
#     -e XIPPIOS_MCP_AGRICULTURE_TOKEN \
#     xippios-mcp
#
# The image runs as the non-root user `xippios`, uid and gid 10001, which USER names by
# number so that a Kubernetes runAsNonRoot check can verify it without a runAsUser. It
# reads its config from /etc/xippios-mcp/host.toml, which the operator mounts, and binds
# 0.0.0.0 on port 8000, so every endpoint is remote: give each a bearer. Every token comes
# from the environment by the name the config's token_env gives it; the image holds no
# config, key or token.
# Both base images are pinned by digest, the tag in a comment, and bumped deliberately.

# python:3.12-slim, 2026-10-28 (Dockerfile comments take a line of their own)
FROM python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159 AS builder

# uv 0.13.6
COPY --from=ghcr.io/astral-sh/uv@sha256:af22a52f5eafef3d78e551599d405c02df61919d18028f0cea8eda93bc9986d0 /uv /usr/local/bin/uv

ENV UV_PYTHON_DOWNLOADS=never \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# The dependencies first, in a layer of their own that a change under src/ leaves cached.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --extra all --no-editable --no-install-project

# Then the project itself, installed into the venv rather than linked to src/, so the
# final stage needs the venv alone.
COPY README.md LICENSE ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --extra all --no-editable


# python:3.12-slim, 2026-10-28, the same base as the builder's
FROM python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159

# The user exists by name too, so `xippios` resolves inside the container.
RUN groupadd --system --gid 10001 xippios \
    && useradd --system --uid 10001 --gid xippios --no-create-home \
       --home-dir /nonexistent --shell /usr/sbin/nologin xippios

COPY --from=builder /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

# By number: a runAsNonRoot check cannot verify a named user.
USER 10001:10001
EXPOSE 8000

ENTRYPOINT ["xippios-mcp"]
CMD ["--config", "/etc/xippios-mcp/host.toml", "--http", "--host", "0.0.0.0", "--port", "8000"]
