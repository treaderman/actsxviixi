"""
Loads Strong's Hebrew and Greek Dictionaries (strongsplus.lexi) into the lexicon table.

Topic format: H### = Hebrew/Aramaic, G### = Greek
Definition is HTML — we parse out transliteration, pronunciation, and definition text.
"""

import sqlite3
import re
import html
import unicodedata
from db import get_connection, init_db

LEXI_PATH = "strongsplus.lexi"

_TAG_RE   = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")


def strip_html(text: str) -> str:
    """
    Strip tags, then decode HTML entities and normalize to NFC.

    The source uses numeric character references for the combining diacritics
    that Strong's transliterations depend on (U+0302 circumflex, U+0304 macron,
    U+0306 breve, ...), so a fixed table of named entities is not enough --
    html.unescape() handles both named and numeric forms.

    Decoding happens AFTER tag stripping so that any entity-encoded angle
    bracket cannot be mistaken for markup. NFC composes "a" + U+0302 into the
    single codepoint "â"; combinations with no precomposed form (e.g. dotless
    "ı" + U+0302) correctly stay decomposed.
    """
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    # A handful of source rows are double-escaped ("&amp;amp;" for a literal
    # "&"). One correct unescape pass leaves no entities behind anywhere else,
    # so a surviving "&amp;" can only be that -- decode it rather than serve it
    # raw. Deliberately narrow: unescaping repeatedly until stable would also
    # corrupt any text that legitimately spells out an entity.
    text = text.replace("&amp;", "&")
    text = unicodedata.normalize("NFC", text)
    return _SPACE_RE.sub(" ", text).strip()


def parse_entry(topic: str, raw_html: str) -> tuple:
    """
    Returns (strongs_num, language, transliteration, definition, kjv_usage)
    Extracts the first <p> block (original word), second (transliteration),
    and remaining text as definition.
    """
    strongs_num = topic.strip()
    language = "Hebrew" if strongs_num.startswith("H") else "Greek"
    # Aramaic entries are a small subset of H-numbers but we keep Hebrew for simplicity;
    # entries that say "Chaldee" in their text are Aramaic
    if "(Chaldee)" in raw_html or "Chaldean" in raw_html:
        language = "Aramaic"

    # Split on </p><p> to get paragraph chunks
    paragraphs = [strip_html(p) for p in re.split(r"</p>\s*<p[^>]*>", raw_html) if p.strip()]
    paragraphs = [p for p in paragraphs if p]

    # Paragraph 0 — original word (Hebrew/Greek characters), skip for storage
    # Paragraph 1 — transliteration (romanized)
    # Paragraph 2 — pronunciation guide (italic)
    # Paragraph 3+ — definition and KJV usage
    transliteration = paragraphs[1] if len(paragraphs) > 1 else None
    pronunciation   = paragraphs[2] if len(paragraphs) > 2 else None
    definition_parts = paragraphs[3:] if len(paragraphs) > 3 else paragraphs[1:]

    # KJV usage is usually the last sentence after a colon-dash ": -"
    kjv_usage = None
    definition = " ".join(definition_parts)
    match = re.search(r":\s*-\s*(.+)$", definition)
    if match:
        kjv_usage = match.group(1).strip()
        definition = definition[:match.start()].strip()

    return (strongs_num, language, transliteration, definition, kjv_usage)


def load() -> None:
    init_db()
    src = sqlite3.connect(LEXI_PATH)
    src.row_factory = sqlite3.Row

    with get_connection() as dst:
        # Clear existing entries
        dst.execute("DELETE FROM lexicon")

        rows = []
        for r in src.execute("SELECT Topic, Definition FROM Lexicon"):
            strongs_num, language, translit, definition, kjv_usage = parse_entry(r["Topic"], r["Definition"])
            rows.append((strongs_num, language, translit, definition, kjv_usage))

        dst.executemany(
            "INSERT INTO lexicon (strongs_num, language, transliteration, definition, kjv_usage) VALUES (?,?,?,?,?)",
            rows,
        )

    src.close()

    hebrew = sum(1 for r in rows if r[1] == "Hebrew")
    aramaic = sum(1 for r in rows if r[1] == "Aramaic")
    greek = sum(1 for r in rows if r[1] == "Greek")
    print(f"Loaded {len(rows)} lexicon entries: {hebrew} Hebrew, {aramaic} Aramaic, {greek} Greek.")


if __name__ == "__main__":
    load()
