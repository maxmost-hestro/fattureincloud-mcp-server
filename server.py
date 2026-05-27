#!/usr/bin/env python3
"""
FattureInCloud MCP Server
Server MCP ufficiale per integrazione con Fatture in Cloud API.

Architettura modulare con tools organizzati per categoria:
- invoices: Gestione fatture emesse
- payments: Pagamenti e scadenze
- clients: Gestione clienti
- expenses: Fatture ricevute e spese
- analytics: Report e statistiche
- info: Informazioni aziendali

Supports three transport modes:
- stdio: For local Claude Code/Desktop usage (default)
- sse: Legacy HTTP/SSE transport (GET /sse)
- streamable-http: MCP spec 2025-03-26, required by claude.ai (POST /)
"""

import asyncio
import contextlib
import logging
import argparse
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.server.sse import SseServerTransport
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.routing import Mount, Route
import uvicorn

# Import modular tools and handlers
from src.tools.invoices import get_invoice_tools, get_invoice_handlers
from src.tools.payments import get_payment_tools, get_payment_handlers
from src.tools.clients import get_client_tools, get_client_handlers
from src.tools.expenses import get_expense_tools, get_expense_handlers
from src.tools.analytics import get_analytics_tools, get_analytics_handlers
from src.tools.info import get_info_tools, get_info_handlers
from src.tools.reminders import get_reminder_tools, get_reminder_handlers
from mcp.types import Tool, TextContent

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("fattureincloud-mcp")

# Create MCP server
server = Server("fattureincloud")

# Collect all tools from modules
logger.info("Collecting tools from all modules...")
ALL_TOOLS = []
ALL_TOOLS.extend(get_invoice_tools())
ALL_TOOLS.extend(get_payment_tools())
ALL_TOOLS.extend(get_client_tools())
ALL_TOOLS.extend(get_expense_tools())
ALL_TOOLS.extend(get_analytics_tools())
ALL_TOOLS.extend(get_info_tools())
ALL_TOOLS.extend(get_reminder_tools())

# Collect all handlers from modules
logger.info("Collecting handlers from all modules...")
ALL_HANDLERS = {}
ALL_HANDLERS.update(get_invoice_handlers())
ALL_HANDLERS.update(get_payment_handlers())
ALL_HANDLERS.update(get_client_handlers())
ALL_HANDLERS.update(get_expense_handlers())
ALL_HANDLERS.update(get_analytics_handlers())
ALL_HANDLERS.update(get_info_handlers())
ALL_HANDLERS.update(get_reminder_handlers())

logger.info(f"Registered {len(ALL_TOOLS)} tools: {list(ALL_HANDLERS.keys())}")

# Register master list_tools handler
@server.list_tools()
async def list_all_tools() -> list[Tool]:
    """Return all tools."""
    return ALL_TOOLS

# Register master call_tool handler
@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Dispatch tool calls to appropriate handlers."""
    handler = ALL_HANDLERS.get(name)
    if handler:
        return await handler(arguments)

    return [TextContent(type="text", text=f"Tool '{name}' not found")]


async def run_stdio():
    """Run the MCP server in stdio mode (for local usage)."""
    logger.info("Starting FattureInCloud MCP Server in STDIO mode...")
    logger.info("Server ready. Registered 20 tools across 7 categories.")

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


async def run_streamable_http(host: str = "0.0.0.0", port: int = 3002):
    """Run the MCP server with streamable HTTP transport (MCP spec 2025-03-26)."""
    logger.info(f"Starting FattureInCloud MCP Server in streamable HTTP mode on {host}:{port}...")
    logger.info("Server ready. Registered 20 tools across 7 categories.")

    session_manager = StreamableHTTPSessionManager(app=server, stateless=True)

    @contextlib.asynccontextmanager
    async def lifespan(app):
        async with session_manager.run():
            yield

    starlette_app = Starlette(
        routes=[Mount("/", app=session_manager.handle_request)],
        lifespan=lifespan,
    )

    config = uvicorn.Config(starlette_app, host=host, port=port, log_level="info")
    server_instance = uvicorn.Server(config)
    await server_instance.serve()


async def run_http(host: str = "0.0.0.0", port: int = 3002):
    """Run the MCP server in HTTP/SSE mode (for remote usage)."""
    logger.info(f"Starting FattureInCloud MCP Server in HTTP/SSE mode on {host}:{port}...")
    logger.info("Server ready. Registered 20 tools across 7 categories.")

    sse = SseServerTransport("/messages")

    async def handle_sse(request):
        async with sse.connect_sse(
            request.scope,
            request.receive,
            request._send,
        ) as streams:
            await server.run(
                streams[0],
                streams[1],
                server.create_initialization_options(),
            )
        return None  # Connection handled by SSE transport

    async def handle_messages(request):
        await sse.handle_post_message(request.scope, request.receive, request._send)
        return None  # Message handled by SSE transport

    starlette_app = Starlette(
        routes=[
            Route("/sse", endpoint=handle_sse),
            Route("/messages", endpoint=handle_messages, methods=["POST"]),
        ],
    )

    config = uvicorn.Config(
        starlette_app,
        host=host,
        port=port,
        log_level="info"
    )
    server_instance = uvicorn.Server(config)
    await server_instance.serve()


def main():
    """Main entry point with argument parsing."""
    parser = argparse.ArgumentParser(
        description="FattureInCloud MCP Server"
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default="stdio",
        help="Transport mode: stdio (default), sse (legacy HTTP/SSE), streamable-http (MCP 2025-03-26)"
    )
    parser.add_argument(
        "--http",
        action="store_true",
        help="Deprecated: use --transport sse instead. Kept for backward compatibility."
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind to in HTTP modes (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=3002,
        help="Port to bind to in HTTP modes (default: 3002)"
    )

    args = parser.parse_args()

    # --http is a deprecated alias for --transport sse (backward compatibility)
    if args.http:
        logger.warning("--http is deprecated, use --transport sse instead")
        args.transport = "sse"

    try:
        if args.transport == "streamable-http":
            asyncio.run(run_streamable_http(args.host, args.port))
        elif args.transport == "sse":
            asyncio.run(run_http(args.host, args.port))
        else:
            asyncio.run(run_stdio())
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
