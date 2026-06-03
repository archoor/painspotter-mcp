# Minimal image so directory indexers (Glama etc.) can build + introspect the
# stdio MCP server. Startup + tools/list need no key; actual tool calls require
# PAINSPOTTER_API_KEY at runtime.
FROM python:3.11-slim

WORKDIR /app
COPY . /app

RUN pip install --no-cache-dir .

ENV PAINSPOTTER_API_BASE=https://painspotter.ai

ENTRYPOINT ["painspotter-mcp"]
