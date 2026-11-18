# Slurp garmin-mcp: MCP server for Garmin Connect.
#
# Serves streamable HTTP on port 8000 as a non-root user and refuses to start
# without GARMIN_MCP_HTTP_TOKEN or GARMIN_MCP_URL_SECRET (or their _FILE
# variants). Garmin tokens live in the /data volume; create them once with:
#   docker run --rm -it -v garmin-tokens:/data --entrypoint garmin-mcp-auth <image>
# For a local stdio client instead: -e GARMIN_MCP_TRANSPORT=stdio

FROM python:3.12-slim AS build

RUN pip install --no-cache-dir uv
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /src

# Dependencies first (locked versions), for layer caching.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY README.md LICENSE NOTICE ./
COPY src/ ./src/
RUN uv sync --frozen --no-dev --no-editable


FROM python:3.12-slim

LABEL org.opencontainers.image.title="Slurp garmin-mcp" \
      org.opencontainers.image.description="MCP server for Garmin Connect" \
      org.opencontainers.image.source="https://github.com/rvartanov/slurp-garmin-mcp" \
      org.opencontainers.image.licenses="MIT"

RUN groupadd --system --gid 10001 garmin-mcp \
    && useradd --system --uid 10001 --gid garmin-mcp --home-dir /data --no-create-home garmin-mcp \
    && install -d -o garmin-mcp -g garmin-mcp -m 0700 /data

COPY --from=build /opt/venv /opt/venv

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/data \
    GARMINTOKENS=/data \
    GARMIN_FIT_DOWNLOAD_DIR=/data/downloads \
    GARMIN_FIT_CONFIG=/data/fit_config.json \
    GARMIN_MCP_TRANSPORT=streamable-http \
    GARMIN_MCP_HOST=0.0.0.0 \
    GARMIN_MCP_PORT=8000 \
    GARMIN_MCP_STATELESS_HTTP=true \
    GARMIN_MCP_REQUIRE_AUTH=true

USER garmin-mcp
WORKDIR /data
VOLUME /data
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import os, sys, urllib.request; sys.exit(0) if os.environ.get('GARMIN_MCP_TRANSPORT') == 'stdio' else urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('GARMIN_MCP_PORT', '8000') + '/healthz', timeout=3)"]

ENTRYPOINT ["garmin-mcp"]
