-- Acts XVII:XI Project — Bible Study API
-- SQLite schema for KJV and associated study data

CREATE TABLE IF NOT EXISTS books (
    id        INTEGER PRIMARY KEY,
    name      TEXT NOT NULL UNIQUE,
    abbrev    TEXT NOT NULL,
    testament TEXT NOT NULL CHECK (testament IN ('OT', 'NT')),
    chapters  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS verses (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id    INTEGER NOT NULL REFERENCES books(id),
    chapter    INTEGER NOT NULL,
    verse      INTEGER NOT NULL,
    text       TEXT NOT NULL,
    UNIQUE (book_id, chapter, verse)
);

CREATE TABLE IF NOT EXISTS commentaries (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id    INTEGER NOT NULL REFERENCES books(id),
    chapter    INTEGER NOT NULL,
    verse      INTEGER,           -- NULL means whole-chapter note
    source     TEXT NOT NULL,     -- e.g. "Matthew Henry", "Geneva"
    text       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lexicon (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    strongs_num  TEXT NOT NULL,   -- e.g. "G3056", "H1254"
    language     TEXT NOT NULL CHECK (language IN ('Greek', 'Hebrew', 'Aramaic')),
    transliteration TEXT,
    definition   TEXT NOT NULL,
    kjv_usage    TEXT            -- comma-separated KJV renderings
);

CREATE INDEX IF NOT EXISTS idx_verses_lookup  ON verses  (book_id, chapter, verse);
CREATE INDEX IF NOT EXISTS idx_verses_text    ON verses  (text);
CREATE INDEX IF NOT EXISTS idx_commentary_ref ON commentaries (book_id, chapter, verse);
CREATE INDEX IF NOT EXISTS idx_strongs        ON lexicon (strongs_num);
