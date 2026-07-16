"""
Acts XVII:XI Bible Study API
Flask server — lightweight JSON endpoints over SQLite
"""

from flask import Flask, jsonify, request, abort
from db import get_connection, init_db

app = Flask(__name__)


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


# ── health ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    with get_connection() as conn:
        verse_count = conn.execute("SELECT COUNT(*) FROM verses").fetchone()[0]
    return jsonify({"status": "ok", "verses_loaded": verse_count})


# ── error handlers ────────────────────────────────────────────────────────────

@app.errorhandler(400)
@app.errorhandler(404)
def http_error(e):
    return jsonify({"error": e.description}), e.code


# ── entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)
