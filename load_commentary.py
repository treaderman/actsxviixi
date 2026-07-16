"""
Loads Expositor's Bible (eb.cmti) into the commentaries table.

The .cmti has three levels:
  BookCommentary    — book-level intro (verse = NULL)
  ChapterCommentary — chapter-level notes (verse = NULL)
  VerseCommentary   — verse/range notes (verse = VerseBegin)

Book numbering in e-Sword: 1=Genesis ... 39=Malachi, 40=Matthew ... 66=Revelation
"""

import sqlite3
import re
from db import get_connection, init_db

CMTI_PATH = "eb.cmti"
SOURCE = "Expositor's Bible"

# e-Sword book number → canonical name in our DB
ESWORD_BOOKS = [
    None,  # 0 = unused
    "Genesis", "Exodus", "Leviticus", "Numbers", "Deuteronomy",
    "Joshua", "Judges", "Ruth", "1 Samuel", "2 Samuel",
    "1 Kings", "2 Kings", "1 Chronicles", "2 Chronicles", "Ezra",
    "Nehemiah", "Esther", "Job", "Psalms", "Proverbs",
    "Ecclesiastes", "Song of Solomon", "Isaiah", "Jeremiah", "Lamentations",
    "Ezekiel", "Daniel", "Hosea", "Joel", "Amos",
    "Obadiah", "Jonah", "Micah", "Nahum", "Habakkuk",
    "Zephaniah", "Haggai", "Zechariah", "Malachi",
    "Matthew", "Mark", "Luke", "John", "Acts",
    "Romans", "1 Corinthians", "2 Corinthians", "Galatians", "Ephesians",
    "Philippians", "Colossians", "1 Thessalonians", "2 Thessalonians",
    "1 Timothy", "2 Timothy", "Titus", "Philemon", "Hebrews",
    "James", "1 Peter", "2 Peter", "1 John", "2 John",
    "3 John", "Jude", "Revelation",
]

_TAG_RE = re.compile(r"<[^>]+>")

def strip_html(text: str) -> str:
    text = _TAG_RE.sub("", text)
    text = text.replace("&rsquo;", "'").replace("&ldquo;", "“") \
               .replace("&rdquo;", "”").replace("&amp;", "&") \
               .replace("&nbsp;", " ").replace("&lsquo;", "‘")
    return " ".join(text.split()).strip()


def load() -> None:
    init_db()
    src = sqlite3.connect(CMTI_PATH)
    src.row_factory = sqlite3.Row

    rows_to_insert: list[tuple] = []  # (book_id, chapter, verse, source, text)

    with get_connection() as dst:
        # build book name → id map
        book_map = {r["name"]: r["id"] for r in dst.execute("SELECT id, name FROM books")}

        def book_id(esword_num: int) -> int | None:
            name = ESWORD_BOOKS[esword_num] if esword_num < len(ESWORD_BOOKS) else None
            return book_map.get(name) if name else None

        # Book-level introductions
        for row in src.execute("SELECT Book, Comments FROM BookCommentary"):
            bid = book_id(row["Book"])
            if bid:
                rows_to_insert.append((bid, 0, None, SOURCE, strip_html(row["Comments"])))

        # Chapter-level notes
        for row in src.execute("SELECT Book, Chapter, Comments FROM ChapterCommentary"):
            bid = book_id(row["Book"])
            if bid:
                rows_to_insert.append((bid, row["Chapter"], None, SOURCE, strip_html(row["Comments"])))

        # Verse / range notes
        for row in src.execute("SELECT Book, ChapterBegin, VerseBegin, Comments FROM VerseCommentary"):
            bid = book_id(row["Book"])
            if bid:
                rows_to_insert.append((bid, row["ChapterBegin"], row["VerseBegin"], SOURCE, strip_html(row["Comments"])))

        dst.executemany(
            "INSERT INTO commentaries (book_id, chapter, verse, source, text) VALUES (?,?,?,?,?)",
            rows_to_insert,
        )

    src.close()
    print(f"Loaded {len(rows_to_insert)} commentary entries from {SOURCE}.")


if __name__ == "__main__":
    load()
