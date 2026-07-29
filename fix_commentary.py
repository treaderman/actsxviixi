"""
1. Adds verse_end column to commentaries (if missing)
2. Clears duplicate data
3. Reloads from eb.cmti with proper range fields
"""
import html
import sqlite3
import re
import unicodedata
from db import get_connection, init_db

CMTI_PATH = "eb.cmti"
SOURCE = "Expositor's Bible"

ESWORD_BOOKS = [
    None,
    "Genesis","Exodus","Leviticus","Numbers","Deuteronomy",
    "Joshua","Judges","Ruth","1 Samuel","2 Samuel",
    "1 Kings","2 Kings","1 Chronicles","2 Chronicles","Ezra",
    "Nehemiah","Esther","Job","Psalms","Proverbs",
    "Ecclesiastes","Song of Solomon","Isaiah","Jeremiah","Lamentations",
    "Ezekiel","Daniel","Hosea","Joel","Amos",
    "Obadiah","Jonah","Micah","Nahum","Habakkuk",
    "Zephaniah","Haggai","Zechariah","Malachi",
    "Matthew","Mark","Luke","John","Acts",
    "Romans","1 Corinthians","2 Corinthians","Galatians","Ephesians",
    "Philippians","Colossians","1 Thessalonians","2 Thessalonians",
    "1 Timothy","2 Timothy","Titus","Philemon","Hebrews",
    "James","1 Peter","2 Peter","1 John","2 John",
    "3 John","Jude","Revelation",
]

_TAG_RE = re.compile(r"<[^>]+>")

def strip_html(text: str) -> str:
    """
    Strip markup, then decode entities.

    This used to replace a hand-written list of six entities, so every other
    one survived into the database as a visible escape code — &quot; alone
    reached 2,198 of the 2,248 rows. html.unescape() covers named and numeric
    forms alike. Same defect as load_lexicon.py had.

    Decoding runs after tag stripping so an entity-encoded angle bracket can
    never be mistaken for markup, and the result is normalised to NFC.
    """
    text = _TAG_RE.sub("", text)
    text = html.unescape(text)
    text = unicodedata.normalize("NFC", text)
    return " ".join(text.split()).strip()


def migrate_schema(conn):
    cols = [r[1] for r in conn.execute("PRAGMA table_info(commentaries)")]
    if "verse_end" not in cols:
        conn.execute("ALTER TABLE commentaries ADD COLUMN verse_end INTEGER")
        print("Added verse_end column.")


def load():
    init_db()
    src = sqlite3.connect(CMTI_PATH)
    src.row_factory = sqlite3.Row

    with get_connection() as dst:
        migrate_schema(dst)

        # Clear existing Expositor's Bible entries
        dst.execute("DELETE FROM commentaries WHERE source = ?", (SOURCE,))
        print("Cleared old entries.")

        book_map = {r["name"]: r["id"] for r in dst.execute("SELECT id, name FROM books")}

        def bid(num):
            name = ESWORD_BOOKS[num] if num < len(ESWORD_BOOKS) else None
            return book_map.get(name) if name else None

        rows = []

        # Book intros — chapter=0, verse=NULL, verse_end=NULL
        for r in src.execute("SELECT Book, Comments FROM BookCommentary"):
            b = bid(r["Book"])
            if b:
                rows.append((b, 0, None, None, SOURCE, strip_html(r["Comments"])))

        # Chapter notes — verse=NULL, verse_end=NULL
        for r in src.execute("SELECT Book, Chapter, Comments FROM ChapterCommentary"):
            b = bid(r["Book"])
            if b:
                rows.append((b, r["Chapter"], None, None, SOURCE, strip_html(r["Comments"])))

        # Verse/range notes — store both VerseBegin and VerseEnd
        for r in src.execute("SELECT Book, ChapterBegin, VerseBegin, VerseEnd, Comments FROM VerseCommentary"):
            b = bid(r["Book"])
            if b:
                rows.append((b, r["ChapterBegin"], r["VerseBegin"], r["VerseEnd"], SOURCE, strip_html(r["Comments"])))

        dst.executemany(
            "INSERT INTO commentaries (book_id, chapter, verse, verse_end, source, text) VALUES (?,?,?,?,?,?)",
            rows,
        )

    src.close()
    print(f"Loaded {len(rows)} commentary entries.")


if __name__ == "__main__":
    load()
