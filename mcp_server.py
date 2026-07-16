"""
Acts XVII:XI — MCP Server
Exposes Bible study tools that Claude (or any MCP client) can call.
Proxies requests to the local Flask API at http://localhost:5000.
"""

import urllib.request
import urllib.parse
import json
from mcp.server.fastmcp import FastMCP

API_BASE = "http://localhost:5000"

mcp = FastMCP(
    name="acts-xvii-xi",
    instructions=(
        "Bible study tools for the King James Bible. "
        "Use get_verse to fetch a specific passage, search_bible to find verses by keyword, "
        "and get_commentary to retrieve study notes on a passage."
    ),
)


def _get(path: str, params: dict) -> dict:
    qs = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    url = f"{API_BASE}{path}?{qs}"
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.load(r)


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
