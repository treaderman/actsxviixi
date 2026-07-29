"""
Acts XVII:XI — combined ASGI entry point.

Serves three things from one process, so the whole project stays on a single
Render service and a single domain:

    /mcp        remote MCP endpoint for AI assistants   (ASGI, Streamable HTTP)
    /           landing page and REST API               (Flask, WSGI)

The REST API is the foundation. The MCP server is a *client* of it — the tools
in mcp_server.py call the same public HTTP endpoints anyone else would, so
there is one implementation of the query logic, not two.

Run with:  uvicorn server:application --host 0.0.0.0 --port $PORT
"""

import contextlib
import os

from a2wsgi import WSGIMiddleware
from starlette.applications import Starlette
from starlette.routing import Mount

# The MCP tools normally reach the REST API over HTTP, which keeps one
# implementation of the query logic and lets mcp_server.py also run standalone
# over stdio against any deployment. Co-hosted, that must NOT go over the
# network: a blocking HTTP call to ourselves would occupy the single event loop
# that has to answer it, and the server deadlocks. "inprocess" makes the tools
# invoke the Flask app directly instead. Set before importing mcp_server, which
# reads this at import time.
os.environ.setdefault("ACTS_API_BASE", "inprocess")

from app import app as flask_app          # noqa: E402  (after env setup)
from mcp_server import mcp                # noqa: E402

mcp_app = mcp.streamable_http_app()


@contextlib.asynccontextmanager
async def lifespan(_app):
    """
    Starlette does not run the lifespan of mounted sub-applications, and the
    MCP session manager will refuse requests if its lifespan never started.
    Delegate to it explicitly.
    """
    async with mcp_app.router.lifespan_context(_app):
        yield


application = Starlette(
    routes=[
        # Splice the MCP route in directly rather than using Mount("/mcp").
        # A Mount only matches "/mcp/..." with a trailing segment, so a bare
        # POST to /mcp would fall through to Flask and 404 — and /mcp with no
        # trailing slash is exactly what MCP clients request.
        *mcp_app.routes,
        # Catch-all: must stay last so it does not shadow /mcp.
        Mount("/", app=WSGIMiddleware(flask_app)),
    ],
    lifespan=lifespan,
)
