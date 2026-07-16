"""
Plain-text KJV loader.

Expected source format — one verse per line:
    Genesis 1:1 In the beginning God created the heaven and the earth.
    Genesis 1:2 And the earth was without form...

Run:
    python loader.py path/to/kjv.txt
"""

import re
import sys
from db import get_connection, init_db

BOOK_META: list[tuple[str, str, str, int]] = [
    # (name, abbrev, testament, chapters)
    ("Genesis", "Gen", "OT", 50), ("Exodus", "Exo", "OT", 40),
    ("Leviticus", "Lev", "OT", 27), ("Numbers", "Num", "OT", 36),
    ("Deuteronomy", "Deu", "OT", 34), ("Joshua", "Jos", "OT", 24),
    ("Judges", "Jdg", "OT", 21), ("Ruth", "Rut", "OT", 4),
    ("1 Samuel", "1Sa", "OT", 31), ("2 Samuel", "2Sa", "OT", 24),
    ("1 Kings", "1Ki", "OT", 22), ("2 Kings", "2Ki", "OT", 25),
    ("1 Chronicles", "1Ch", "OT", 29), ("2 Chronicles", "2Ch", "OT", 36),
    ("Ezra", "Ezr", "OT", 10), ("Nehemiah", "Neh", "OT", 13),
    ("Esther", "Est", "OT", 10), ("Job", "Job", "OT", 42),
    ("Psalms", "Psa", "OT", 150),
 ("Proverbs", "Pro", "OT", 31),
    ("Ecclesiastes", "Ecc", "OT", 12), ("Song of Solomon", "Son", "OT", 8),
    ("Isaiah", "Isa", "OT", 66), ("Jeremiah", "Jer", "OT", 52),
    ("Lamentations", "Lam", "OT", 5), ("Ezekiel", "Eze", "OT", 48),
    ("Daniel", "Dan", "OT", 12), ("Hosea", "Hos", "OT", 14),
    ("Joel", "Joe", "OT", 3), ("Amos", "Amo", "OT", 9),
    ("Obadiah", "Oba", "OT", 1), ("Jonah", "Jon", "OT", 4),
    ("Micah", "Mic", "OT", 7), ("Nahum", "Nah", "OT", 3),
    ("Habakkuk", "Hab", "OT", 3), ("Zephaniah", "Zep", "OT", 3),
    ("Haggai", "Hag", "OT", 2), ("Zechariah", "Zec", "OT", 14),
    ("Malachi", "Mal", "OT", 4),
    ("Matthew", "Mat", "NT", 28), ("Mark", "Mar", "NT", 16),
    ("Luke", "Luk", "NT", 24), ("John", "Joh", "NT", 21),
    ("Acts", "Act", "NT", 28), ("Romans", "Rom", "NT", 16),
    ("1 Corinthians", "1Co", "NT", 16), ("2 Corinthians", "2Co", "NT", 13),
    ("Galatians", "Gal", "NT", 6), ("Ephesians", "Eph", "NT", 6),
    ("Philippians", "Php", "NT", 4), ("Colossians", "Col", "NT", 4),
    ("1 Thessalonians", "1Th", "NT", 5), ("2 Thessalonians", "2Th", "NT", 3),
    ("1 Timothy", "1Ti", "NT", 6), ("2 Timothy", "2Ti", "NT", 4),
    ("Titus", "Tit", "NT", 3), ("Philemon", "Phm", "NT", 1),
    ("Hebrews", "Heb", "NT", 13), ("James", "Jas", "NT", 5),
    ("1 Peter", "1Pe", "NT", 5), ("2 Peter", "2Pe", "NT", 3),
    ("1 John", "1Jo", "NT", 5), ("2 John", "2Jo", "NT", 1),
    ("3 John", "3Jo", "NT", 1), ("Jude", "Jud", "NT", 1),
    ("Revelation", "Rev", "NT", 22),
]

# Longest names first so the regex matches greedily
_BOOK_NAMES = sorted({b[0] for b in BOOK_META} | {"Psalm"}, key=len, reverse=True)
_LINE_RE = re.compile(
    r"^(" + "|".join(re.escape(b) for b in _BOOK_NAMES) + r")\s+(\d+):(\d+)[\s\t]+(.+)$"
)


def seed_books(conn: sqlite3.Connection) -> dict[str, int]:
    conn.executemany(
        "INSERT OR IGNORE INTO books (name, abbrev, testament, chapters) VALUES (?,?,?,?)",
        BOOK_META,
    )
    rows = conn.execute("SELECT id, name FROM books").fetchall()
    return {row["name"]: row["id"] for row in rows}


def load_text(path: str) -> None:
    init_db()
    with get_connection() as conn:
        book_ids = seed_books(conn)
        verses: list[tuple[int, int, int, str]] = []
        skipped = 0

        with open(path, encoding="utf-8-sig") as fh:
            for lineno, raw in enumerate(fh, 1):
                line = raw.strip()
                if not line:
                    continue
                m = _LINE_RE.match(line)
                if not m:
                    skipped += 1
                    if skipped <= 5:
                        print(f"  skip line {lineno}: {line[:80]}".encode("ascii", "replace").decode())
                    continue
                book_name = m.group(1)
                # normalize known aliases to canonical names
                book_name = {"Psalm": "Psalms"}.get(book_name, book_name)
                chapter, verse, text = int(m.group(2)), int(m.group(3)), m.group(4)
                book_id = book_ids.get(book_name)
                if book_id is None:
                    print(f"  unknown book '{book_name}' on line {lineno}")
                    skipped += 1
                    continue
                verses.append((book_id, chapter, verse, text))

        conn.executemany(
            "INSERT OR REPLACE INTO verses (book_id, chapter, verse, text) VALUES (?,?,?,?)",
            verses,
        )
        print(f"Loaded {len(verses)} verses ({skipped} lines skipped).")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python loader.py <path/to/kjv.txt>")
        sys.exit(1)
    load_text(sys.argv[1])
