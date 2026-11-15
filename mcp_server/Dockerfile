# MCP server for the Frontline Copilot tools.
# Build from the repository root:  docker build -f mcp_server/Dockerfile -t frontline-mcp .
# Run:  docker run --rm -p 8000:8000 -e DATABRICKS_HOST=... -e DATABRICKS_CLIENT_ID=... \
#         -e DATABRICKS_CLIENT_SECRET=... -e SQL_WAREHOUSE_ID=... frontline-mcp
# Credentials come from the environment only. Nothing secret is copied into the image.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8000

WORKDIR /app

# Dependencies first, so a code change does not reinstall them.
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install ".[mcp,models]"

COPY config ./config
COPY mcp_server ./mcp_server

RUN useradd --create-home --uid 10001 appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

# Any HTTP answer from the server, including "method not allowed", means it is up.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import os, urllib.request, urllib.error; \
url = 'http://127.0.0.1:' + os.environ.get('MCP_PORT', '8000') + '/mcp'; \
exec('try:\n    urllib.request.urlopen(url, timeout=3)\nexcept urllib.error.HTTPError:\n    pass')"

CMD ["python", "-m", "mcp_server.server", "--transport", "streamable-http"]
