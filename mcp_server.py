"""
Acts XVII:XI — MCP Server
Exposes Bible study tools that Claude (or any MCP client) can call.
Proxies requests to the local Flask API at http://localhost:5000.
"""

import os
import urllib.request
import urllib.parse
import json
from mcp.server.fastmcp import FastMCP

# Point at the live API by setting ACTS_API_BASE, e.g. https://actsxviixi.onrender.com
API_BASE = os.environ.get("ACTS_API_BASE", "http://localhost:5000").rstrip("/")
API_KEY = os.environ.get("ACTS_API_KEY", "")

mcp = FastMCP(
    name="acts-xvii-xi",
    instructions=(
        "Bible study tools for the King James Bible. "
        "Use get_verse to fetch a specific passage, search_bible to find verses by keyword, "
        "and get_commentary to retrieve study notes on a passage."
    ),
    # Every tool here is a pure read, so there is no session state worth
    # keeping. Stateless mode avoids needing request affinity when hosted.
    stateless_http=True,
    # Exposed at exactly /mcp — server.py splices this route into the outer
    # ASGI app rather than mounting it. See the note there.
    streamable_http_path="/mcp",
)


# When the MCP server is co-hosted with the API in one process (see server.py),
# it must NOT reach the API over HTTP. The tool would block the single event
# loop that has to serve that very request, and the server deadlocks against
# itself. Calling the WSGI app directly keeps it in-process and synchronous.
IN_PROCESS = API_BASE == "inprocess"

_wsgi_client = None


def _inprocess_get(path: str, qs: str) -> dict:
    global _wsgi_client
    if _wsgi_client is None:
        from app import app as flask_app
        _wsgi_client = flask_app.test_client()

    response = _wsgi_client.get(f"{path}?{qs}")
    payload = response.get_json(silent=True)
    if payload is None:
        return {"error": f"Unexpected non-JSON response ({response.status_code})"}
    return payload


def _get(path: str, params: dict) -> dict:
    qs = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})

    if IN_PROCESS:
        return _inprocess_get(path, qs)

    req = urllib.request.Request(f"{API_BASE}{path}?{qs}")
    if API_KEY:
        req.add_header("X-API-Key", API_KEY)

    # Render's free tier sleeps when idle; a cold start can take up to a minute.
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        try:
            return {"error": json.load(e)["error"], "status": e.code}
        except Exception:
            return {"error": f"HTTP {e.code} from {API_BASE}{path}", "status": e.code}
    except urllib.error.URLError as e:
        return {
            "error": f"Could not reach the Bible API at {API_BASE} ({e.reason}). "
                     "If using the local server, make sure Flask is running."
        }


# ── tools ──────────────────────────────────────────────────────────────────

@mcp.tool()
def get_verse(book: str, chapter: int, verse: int, end_verse: int | None = None) -> dict:
    """
    Fetch a verse or range of verses from the King James Bible.

    Args:
        book:      Full book name (e.g. "John") or abbreviation (e.g. "Joh").
        chapter:   Chapter number.
        verse:     Starting verse number.
        end_verse: Optional ending verse for a range (e.g. end_verse=5 returns verses 1-5).

    Returns a dict with ref, book, chapter, verse, and text fields.
    For a range, returns ref and a list of verse dicts.
    """
    params = {"book": book, "chapter": chapter, "verse": verse}
    if end_verse is not None:
        params["end"] = end_verse
    return _get("/verse", params)


@mcp.tool()
def search_bible(
    query: str,
    testament: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """
    Search the King James Bible by keyword or phrase.

    Args:
        query:     Word or phrase to search for (case-insensitive).
        testament: Optional filter — "OT" for Old Testament, "NT" for New Testament.
        limit:     Max results to return (default 20, max 100).
        offset:    Pagination offset for large result sets.

    Returns total match count plus a list of matching verses with ref and text.
    """
    return _get("/search", {"q": query, "testament": testament, "limit": limit, "offset": offset})


@mcp.tool()
def get_commentary(
    book: str,
    chapter: int,
    verse: int | None = None,
    source: str | None = None,
) -> dict:
    """
    Retrieve commentary notes for a passage.

    Args:
        book:    Full book name or abbreviation.
        chapter: Chapter number.
        verse:   Verse number (optional — omit for whole-chapter notes).
        source:  Filter by commentary source name, e.g. "Matthew Henry".

    Returns a list of notes with source and text fields.
    """
    return _get("/commentary", {"book": book, "chapter": chapter, "verse": verse, "source": source})


@mcp.tool()
def lookup_lexicon(num: str | None = None, q: str | None = None, lang: str | None = None) -> dict:
    """
    Look up a Strong's Hebrew or Greek lexicon entry.

    Args:
        num:  Strong's number for an exact lookup, e.g. "G3056" or "H1254".
        q:    Keyword to search definitions (used when num is not provided).
        lang: Optional language filter — "Greek", "Hebrew", or "Aramaic".

    Returns the entry with transliteration, definition, and KJV usage.
    """
    params: dict = {}
    if num:
        params["num"] = num
    if q:
        params["q"] = q
    if lang:
        params["lang"] = lang
    return _get("/lexicon", params)


@mcp.tool()
def bible_health() -> dict:
    """
    Check that the Bible API is running and return the number of verses loaded.
    Useful for confirming the server is reachable before making study queries.
    """
    return _get("/health", {})


# ── entry point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run(transport="stdio")
