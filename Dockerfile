# FattureInCloud MCP Server
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .
COPY src/ ./src/

EXPOSE 3002

# Default: streamable HTTP for remote/container deployments
CMD ["python", "server.py", "--transport", "streamable-http"]
