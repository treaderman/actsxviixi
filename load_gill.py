"""
Load John Gill's Exposition of the Entire Bible into the commentaries table.

The source is a 78MB binary Word document (OLE2), not text, so extract it first:

    antiword -w 0 "John Gill's Commentary on the Bible.doc" > gill.txt

Usage:  python load_gill.py gill.txt

Layout of the extracted text — each verse is introduced by a bare reference
line, and any book or chapter introduction is bundled into the verse 1 block:

    Genesis 1:1
    INTRODUCTION TO GENESIS
    <book introduction>
    INTRODUCTION TO GENESIS 1
    <chapter introduction>
    Ver. 1. In the beginning God created...

Those three kinds of note are stored separately, following the convention the
Expositor's data already uses:

    chapter 0, verse NULL   book introduction
    chapter N, verse NULL   chapter introduction
    chapter N, verse V      verse commentary
"""

import re
import sqlite3
import sys
import unicodedata
from pathlib import Path

from db import get_connection

SOURCE = "John Gill"

# Word conversion leaves image placeholders behind.
PIC = re.compile(r"\[pic\]")
BLANK_RUN = re.compile(r"\n{3,}")
INTRO = re.compile(r"^INTRODUCTION TO (.+?)\s*$", re.M)
VERSE_MARK = re.compile(r"^Ver\.\s", re.M)

# Pull a chapter number out of an introduction heading.
#
# The number must follow alphabetic text, which is what separates a chapter
# heading from a book whose name merely starts with a digit:
#
#   "ISAIAH 60."                   -> chapter 60   (trailing period is common)
#   "I PETER 1 In this chapter..." -> chapter 1    (heading ran into the body
#                                                   with no line break)
#   "1 CHRONICLES"                 -> no match, so a book introduction
#   "THE BOOK OF RUTH"             -> no match, so a book introduction
CHAPTER_IN_HEADING = re.compile(
    r"^(?P<name>.*[A-Za-z])\s+(?P<num>\d+)\b\.?\s*(?P<rest>.*)$", re.S
)


def clean(text: str) -> str:
    text = PIC.sub("", text)
    text = unicodedata.normalize("NFC", text)
    text = BLANK_RUN.sub("\n\n", text)
    return text.strip()


def reference_pattern(book_names) -> re.Pattern:
    """
    Match a line that is exactly "<Book> <chapter>:<verse>".

    Longest name first so "1 John" is not matched as "John", and anchored to
    whole lines so the thousands of inline cross-references Gill cites
    ("see Ge 1:1") are not mistaken for section headers.
    """
    alternatives = "|".join(
        re.escape(name) for name in sorted(book_names, key=len, reverse=True)
    )
    return re.compile(rf"^({alternatives})\s+(\d+):(\d+)\s*$", re.M)


def split_intros(book: str, chapter: int, blob: str):
    """
    Yield (chapter, verse, text) for the introduction material that precedes a
    block's first "Ver." marker. A heading ending in a number introduces that
    chapter; otherwise it introduces the book, which is stored at chapter 0.
    """
    marks = list(INTRO.finditer(blob))
    if not marks:
        return

    for i, mark in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(blob)
        body = blob[mark.end():end]

        found = CHAPTER_IN_HEADING.match(mark.group(1))
        if found:
            target = int(found.group("num"))
            # Where the heading ran into the paragraph, that text belongs to
            # the body, not the heading — put it back rather than dropping it.
            trailing = found.group("rest").strip()
            if trailing:
                body = f"{trailing}\n{body}"
        else:
            target = 0

        body = clean(body)
        if body:
            yield (target, None, body)


def parse(text: str, book_ids: dict):
    """Yield (book_id, chapter, verse, text) rows."""
    pattern = reference_pattern(book_ids)
    matches = list(pattern.finditer(text))
    if not matches:
        raise SystemExit("No reference headers found — is this the right file?")

    for i, match in enumerate(matches):
        book, chapter, verse = match.group(1), int(match.group(2)), int(match.group(3))
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        blob = text[match.end():end]
        book_id = book_ids[book]

        first_verse = VERSE_MARK.search(blob)
        head = blob[: first_verse.start()] if first_verse else blob

        for ch, vs, body in split_intros(book, chapter, head):
            yield (book_id, ch, vs, body)

        if first_verse:
            body = clean(blob[first_verse.start():])
            if body:
                yield (book_id, chapter, verse, body)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python load_gill.py <extracted-gill.txt>")

    path = Path(sys.argv[1])
    if not path.exists():
        raise SystemExit(f"No such file: {path}")

    text = path.read_text(encoding="utf-8", errors="replace")

    with get_connection() as conn:
        book_ids = {r["name"]: r["id"] for r in conn.execute("SELECT id, name FROM books")}
        if not book_ids:
            raise SystemExit("books table is empty — load the KJV first")

        # Idempotent: a re-run replaces this source rather than duplicating it.
        removed = conn.execute(
            "DELETE FROM commentaries WHERE source = ?", (SOURCE,)
        ).rowcount
        if removed:
            print(f"Removed {removed:,} existing {SOURCE} rows")

        rows = [
            (book_id, chapter, verse, SOURCE, body)
            for book_id, chapter, verse, body in parse(text, book_ids)
        ]
        conn.executemany(
            "INSERT INTO commentaries (book_id, chapter, verse, source, text) "
            "VALUES (?, ?, ?, ?, ?)",
            rows,
        )

    verses = sum(1 for r in rows if r[2] is not None)
    print(f"Loaded {len(rows):,} {SOURCE} notes "
          f"({verses:,} verse-level, {len(rows) - verses:,} introductions)")


if __name__ == "__main__":
    main()
