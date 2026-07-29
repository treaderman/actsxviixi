"""
Acts XVII:XI Bible Study API
Flask server — lightweight JSON endpoints over SQLite
"""

import os

from flask import Flask, jsonify, request, abort
from flask_limiter import Limiter
from db import get_connection, init_db

app = Flask(__name__)

# Comma-separated list of valid keys. Unset/empty → auth disabled (local dev).
API_KEYS = {k.strip() for k in os.environ.get("API_KEYS", "").split(",") if k.strip()}

# Endpoints reachable without a key — uptime checks and the landing docs.
PUBLIC_PATHS = {"/health", "/"}


# ── rate limiting ─────────────────────────────────────────────────────────────

def _client_ip() -> str:
    """
    The real caller's address.

    Render fronts services with Cloudflare, so request.remote_addr is a proxy —
    keying on it would put every caller in the world into one shared bucket and
    rate-limit them collectively. Cloudflare sets CF-Connecting-IP to the
    original client, which is the value to trust here.

    X-Forwarded-For is a spoofable fallback, but the only thing it guards is a
    courtesy limit on public-domain text, so that trade is fine.
    """
    cf = request.headers.get("CF-Connecting-IP")
    if cf:
        return cf.strip()
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"


RATE_LIMITS = [
    limit.strip()
    for limit in os.environ.get("RATE_LIMITS", "60 per minute; 2000 per hour").split(";")
    if limit.strip()
]

limiter = Limiter(
    key_func=_client_ip,
    app=app,
    default_limits=RATE_LIMITS,
    storage_uri="memory://",   # single worker; resets on restart
    headers_enabled=True,      # advertise the limit so clients can self-pace
)


@limiter.request_filter
def _exempt_loopback() -> bool:
    """
    The co-hosted MCP server (see server.py) reaches these endpoints over
    loopback. Without this it would spend the public per-IP budget on itself
    and throttle every AI client collectively.

    Traffic from outside always arrives through Cloudflare, which sets
    CF-Connecting-IP, so a real client cannot reach this branch by forging
    X-Forwarded-For.
    """
    return _client_ip() in {"127.0.0.1", "::1"}


# ── auth ──────────────────────────────────────────────────────────────────────

@app.before_request
def require_api_key():
    if not API_KEYS or request.path in PUBLIC_PATHS:
        return None

    key = request.headers.get("X-API-Key") or request.args.get("key", "")
    if key not in API_KEYS:
        return jsonify({
            "error": "Invalid or missing API key. "
                     "Pass it as the X-API-Key header or a 'key' query param."
        }), 401
    return None


# ── helpers ──────────────────────────────────────────────────────────────────

def _book_id(conn, book_name: str) -> int | None:
    row = conn.execute(
        "SELECT id FROM books WHERE name = ? OR abbrev = ? COLLATE NOCASE",
        (book_name, book_name),
    ).fetchone()
    return row["id"] if row else None


def _verse_row_to_dict(row) -> dict:
    return {
        "book":    row["name"],
        "chapter": row["chapter"],
        "verse":   row["verse"],
        "text":    row["text"],
        "ref":     f"{row['name']} {row['chapter']}:{row['verse']}",
    }


# ── endpoints ─────────────────────────────────────────────────────────────────

@app.get("/verse")
def get_verse():
    """
    Fetch a single verse or a range.

    Query params:
        book    — full name or abbreviation (required)
        chapter — integer (required)
        verse   — integer (required unless range)
        end     — last verse of a range (optional)
    """
    book_name = request.args.get("book", "").strip()
    chapter   = request.args.get("chapter", type=int)
    verse     = request.args.get("verse",   type=int)
    end       = request.args.get("end",     type=int)

    if not book_name or chapter is None or verse is None:
        abort(400, "book, chapter, and verse are required")

    with get_connection() as conn:
        book_id = _book_id(conn, book_name)
        if book_id is None:
            abort(404, f"Book '{book_name}' not found")

        if end and end > verse:
            rows = conn.execute(
                """SELECT b.name, v.chapter, v.verse, v.text
                   FROM verses v JOIN books b ON b.id = v.book_id
                   WHERE v.book_id = ? AND v.chapter = ?
                     AND v.verse BETWEEN ? AND ?
                   ORDER BY v.verse""",
                (book_id, chapter, verse, end),
            ).fetchall()
            if not rows:
                abort(404, "No verses found for that range")
            return jsonify({
                "ref":    f"{rows[0]['name']} {chapter}:{verse}-{end}",
                "verses": [_verse_row_to_dict(r) for r in rows],
            })

        row = conn.execute(
            """SELECT b.name, v.chapter, v.verse, v.text
               FROM verses v JOIN books b ON b.id = v.book_id
               WHERE v.book_id = ? AND v.chapter = ? AND v.verse = ?""",
            (book_id, chapter, verse),
        ).fetchone()
        if row is None:
            abort(404, f"{book_name} {chapter}:{verse} not found")
        return jsonify(_verse_row_to_dict(row))


@app.get("/search")
def search():
    """
    Full-text search across all verses.

    Query params:
        q        — search string (required)
        testament — OT | NT (optional filter)
        limit    — max results, default 20, max 100
        offset   — pagination offset, default 0
    """
    q         = request.args.get("q", "").strip()
    testament = request.args.get("testament", "").upper()
    limit     = min(request.args.get("limit", 20, type=int), 100)
    offset    = request.args.get("offset", 0, type=int)

    if not q:
        abort(400, "q is required")

    testament_filter = ""
    params: list = [f"%{q}%"]
    if testament in ("OT", "NT"):
        testament_filter = "AND b.testament = ?"
        params.append(testament)

    params += [limit, offset]

    with get_connection() as conn:
        rows = conn.execute(
            f"""SELECT b.name, b.testament, v.chapter, v.verse, v.text
                FROM verses v JOIN books b ON b.id = v.book_id
                WHERE v.text LIKE ? {testament_filter}
                ORDER BY b.id, v.chapter, v.verse
                LIMIT ? OFFSET ?""",
            params,
        ).fetchall()

        total = conn.execute(
            f"""SELECT COUNT(*) FROM verses v JOIN books b ON b.id = v.book_id
                WHERE v.text LIKE ? {testament_filter}""",
            params[:-2],
        ).fetchone()[0]

    return jsonify({
        "query":     q,
        "total":     total,
        "limit":     limit,
        "offset":    offset,
        "results": [
            {
                "ref":       f"{r['name']} {r['chapter']}:{r['verse']}",
                "book":      r["name"],
                "testament": r["testament"],
                "chapter":   r["chapter"],
                "verse":     r["verse"],
                "text":      r["text"],
            }
            for r in rows
        ],
    })


@app.get("/commentary")
def get_commentary():
    """
    Retrieve commentary notes for a passage.

    Query params:
        book    — full name or abbreviation (required)
        chapter — integer (required)
        verse   — integer (optional; omit for whole-chapter notes)
        source  — filter by commentary source (optional)
    """
    book_name = request.args.get("book", "").strip()
    chapter   = request.args.get("chapter", type=int)
    verse     = request.args.get("verse",   type=int)
    source    = request.args.get("source",  "").strip()

    if not book_name or chapter is None:
        abort(400, "book and chapter are required")

    source_filter = "AND c.source = ?" if source else ""

    with get_connection() as conn:
        book_id = _book_id(conn, book_name)
        if book_id is None:
            abort(404, f"Book '{book_name}' not found")

        if verse is not None:
            # Match exact verse OR any range that contains the requested verse
            verse_filter = "AND c.verse <= ? AND (c.verse_end IS NULL OR c.verse_end >= ?)"
            params = [book_id, chapter, verse, verse]
        else:
            verse_filter = "AND c.verse IS NULL"
            params = [book_id, chapter]

        if source:
            params.append(source)

        rows = conn.execute(
            f"""SELECT c.id, b.name, c.chapter, c.verse, c.verse_end, c.source, c.text
                FROM commentaries c JOIN books b ON b.id = c.book_id
                WHERE c.book_id = ? AND c.chapter = ?
                  {verse_filter} {source_filter}
                ORDER BY c.verse, c.source""",
            params,
        ).fetchall()

    ref = f"{book_name} {chapter}" + (f":{verse}" if verse is not None else "")
    return jsonify({
        "ref":    ref,
        "count":  len(rows),
        "notes": [
            {
                "id":        r["id"],
                "source":    r["source"],
                "verse":     r["verse"],
                "verse_end": r["verse_end"],
                "text":      r["text"],
            }
            for r in rows
        ],
    })


# ── lexicon ───────────────────────────────────────────────────────────────────

@app.get("/lexicon")
def get_lexicon():
    """
    Look up a Strong's number or search by keyword.

    Query params:
        num    — Strong's number, e.g. G3056 or H1254 (exact lookup)
        q      — keyword search in definitions (used if num not provided)
        lang   — filter by Greek | Hebrew | Aramaic (optional)
        limit  — max results for keyword search, default 20
    """
    num  = request.args.get("num",  "").strip().upper()
    q    = request.args.get("q",    "").strip()
    lang = request.args.get("lang", "").strip().capitalize()
    limit = min(request.args.get("limit", 20, type=int), 100)

    if not num and not q:
        abort(400, "num or q is required")

    def row_to_dict(r):
        return {
            "strongs_num":      r["strongs_num"],
            "language":         r["language"],
            "transliteration":  r["transliteration"],
            "definition":       r["definition"],
            "kjv_usage":        r["kjv_usage"],
        }

    with get_connection() as conn:
        if num:
            row = conn.execute(
                "SELECT * FROM lexicon WHERE strongs_num = ?", (num,)
            ).fetchone()
            if row is None:
                abort(404, f"Strong's number '{num}' not found")
            return jsonify(row_to_dict(row))

        lang_filter = "AND language = ?" if lang in ("Greek", "Hebrew", "Aramaic") else ""
        params = [f"%{q}%"]
        if lang_filter:
            params.append(lang)
        params.append(limit)

        rows = conn.execute(
            f"""SELECT * FROM lexicon
                WHERE definition LIKE ? {lang_filter}
                ORDER BY strongs_num LIMIT ?""",
            params,
        ).fetchall()
        return jsonify({
            "query": q, "count": len(rows),
            "results": [row_to_dict(r) for r in rows],
        })


# ── index ─────────────────────────────────────────────────────────────────────

ENDPOINTS = [
    ("GET /verse",      "Fetch a verse or range",
     "/verse?book=John&chapter=3&verse=16"),
    ("GET /search",     "Full-text search, optional OT/NT filter",
     "/search?q=living+water&testament=NT&limit=20"),
    ("GET /commentary", "Expositor's Bible notes for a passage",
     "/commentary?book=John&chapter=3&verse=16"),
    ("GET /lexicon",    "Strong's Hebrew/Greek entry or keyword search",
     "/lexicon?num=G3056"),
    ("GET /health",     "Server status and row counts", "/health"),
]


def _counts() -> dict:
    with get_connection() as conn:
        return {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("books", "verses", "commentaries", "lexicon")
        }


@app.get("/")
@limiter.exempt
def index():
    """
    Landing page. Serves HTML to browsers and JSON to everything else, so the
    domain is readable by a person without breaking programmatic clients.
    """
    counts = _counts()

    accept = request.accept_mimetypes
    wants_html = accept["text/html"] > accept["application/json"]
    if not wants_html:
        return jsonify({
            "name":        "Acts XVII:XI",
            "description": "Free, open-source Bible study API — KJV verses, "
                           "Expositor's Bible commentary, and Strong's lexicon.",
            "source":      "https://github.com/treaderman/actsxviixi",
            "auth_required": bool(API_KEYS),
            "rate_limits": RATE_LIMITS,
            "bulk_download": "https://github.com/treaderman/actsxviixi/releases",
            "data":        counts,
            "endpoints": [
                {"endpoint": name, "description": desc, "example": example}
                for name, desc, example in ENDPOINTS
            ],
        })

    rows = "\n".join(
        f'<tr><td><code>{name}</code></td><td>{desc}</td>'
        f'<td><a href="{example}"><code>{example}</code></a></td></tr>'
        for name, desc, example in ENDPOINTS
    )
    limits = " and ".join(RATE_LIMITS)
    return f"""<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Acts XVII:XI — Bible Study API</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ font-family: system-ui, sans-serif; line-height: 1.6; margin: 0 auto;
         max-width: 46rem; padding: 2.5rem 1.25rem; }}
  h1 {{ margin-bottom: .25rem; font-size: 1.75rem; }}
  .verse {{ color: #6b6b6b; font-style: italic; margin: 0 0 2rem; }}
  table {{ border-collapse: collapse; width: 100%; display: block;
           overflow-x: auto; }}
  th, td {{ text-align: left; padding: .5rem .6rem;
            border-bottom: 1px solid rgba(128,128,128,.3); vertical-align: top; }}
  code {{ font-size: .9em; }}
  ul {{ padding-left: 1.2rem; }}
  footer {{ margin-top: 2.5rem; font-size: .9em; color: #6b6b6b; }}
</style>
<h1>Acts XVII:XI</h1>
<p class="verse">&ldquo;&hellip;searched the scriptures daily, whether those
things were so.&rdquo;</p>
<p>A free, open-source Bible study API serving structured JSON.
<strong>No key required.</strong></p>
<ul>
  <li><strong>{counts['verses']:,}</strong> KJV verses across
      <strong>{counts['books']}</strong> books</li>
  <li><strong>{counts['commentaries']:,}</strong> Expositor's Bible entries</li>
  <li><strong>{counts['lexicon']:,}</strong> Strong's lexicon entries</li>
</ul>
<table>
  <thead><tr><th>Endpoint</th><th>Description</th><th>Example</th></tr></thead>
  <tbody>
{rows}
  </tbody>
</table>
<footer>
  Rate limited to {limits} per IP, as a courtesy so the service stays up for
  everyone. Need bulk or offline access? Download the whole database from
  <a href="https://github.com/treaderman/actsxviixi/releases">Releases</a>.
  <br><br>
  Source on <a href="https://github.com/treaderman/actsxviixi">GitHub</a>.
  All texts are public domain.
</footer>
</html>"""


# ── health ────────────────────────────────────────────────────────────────────

@app.get("/health")
@limiter.exempt
def health():
    counts = _counts()
    return jsonify({
        "status":            "ok",
        "auth_required":     bool(API_KEYS),
        "verses_loaded":     counts["verses"],   # kept for existing clients
        "books_loaded":      counts["books"],
        "commentaries_loaded": counts["commentaries"],
        "lexicon_loaded":    counts["lexicon"],
    })


# ── error handlers ────────────────────────────────────────────────────────────

@app.errorhandler(400)
@app.errorhandler(404)
def http_error(e):
    return jsonify({"error": e.description}), e.code


@app.errorhandler(429)
def rate_limited(e):
    return jsonify({
        "error": "Rate limit exceeded. This is a free, open API — please pace "
                 "your requests.",
        "limit": str(e.description),
        "bulk_access": "For heavy or offline use, download the whole database: "
                       "https://github.com/treaderman/actsxviixi/releases",
    }), 429


# ── entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)
