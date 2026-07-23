# Acts XVII:XI Project — Handoff Document
**Last updated:** July 15, 2026

---

## What This Is
A free, open-source Bible study API serving KJV verses, Expositor's Bible commentary, and Strong's Hebrew/Greek lexicon as structured JSON. Designed to be queried by AI assistants (Claude) via an MCP connector.

**Domain:** actsxviixi.org (purchased on Namecheap, not yet pointed at Render)
**GitHub:** https://github.com/treaderman/actsxviixi
**Live API:** https://actsxviixi.onrender.com

---

## Current State

### What's Working
- Flask API live on Render at `actsxviixi.onrender.com`
- `/verse` — fetch single verse or range
- `/search` — full-text keyword search with OT/NT filter
- `/commentary` — Expositor's Bible notes by passage
- `/lexicon` — Strong's Hebrew/Greek lookup by number or keyword
- `/health` — server status and verse count
- MCP connector (`mcp_server.py`) registered in Claude Desktop

### What's Limited Right Now
- Only 13 sample verses on the live server (full KJV not yet uploaded)
- Commentary and lexicon tables empty on live server
- Domain not yet pointed at Render
- MCP connector only works locally (requires Flask running on localhost:5000)

---

## Local Setup
**Project folder:** `C:\Users\mhmco\Projects\Bible_Commentary_App`
_(Moved out of OneDrive on 2026-07-23 to avoid Git/SQLite sync conflicts.)_

**Local database has full data:**
- 31,102 KJV verses (Pure Cambridge Edition)
- 2,248 Expositor's Bible commentary entries
- 14,197 Strong's lexicon entries (7,999 Hebrew + 676 Aramaic + 5,522 Greek)

**To run locally:**
```
cd "C:\Users\mhmco\Projects\Bible_Commentary_App"
python app.py
```

**Source data files (local only, not in GitHub):**
- `kjv.txt` — in Downloads folder (`C:\Users\mhmco\Downloads\kjv.txt`)
- `eb.cmti` — Expositor's Bible (100MB, in project folder)
- `strongsplus.lexi` — Strong's dictionaries (14MB, in project folder)

---

## Files
| File | Purpose |
|---|---|
| `app.py` | Flask API — all endpoints |
| `db.py` | Database connection helper |
| `schema.sql` | SQLite schema (books, verses, commentaries, lexicon) |
| `loader.py` | Loads KJV plain-text into database |
| `load_commentary.py` | Loads Expositor's Bible from `.cmti` file |
| `fix_commentary.py` | Fixed duplicate data + added verse_end range support |
| `load_lexicon.py` | Loads Strong's from `.lexi` file |
| `mcp_server.py` | MCP connector — exposes 5 tools to Claude |
| `requirements.txt` | flask, gunicorn |
| `sample_kjv.txt` | 13 sample verses for testing |

---

## API Endpoints

```
GET /verse?book=John&chapter=3&verse=16
GET /verse?book=Psalms&chapter=23&verse=1&end=3
GET /search?q=living+water&testament=NT&limit=20
GET /commentary?book=John&chapter=3&verse=16
GET /lexicon?num=G3056
GET /lexicon?q=atonement&lang=Hebrew
GET /health
```

---

## MCP Connector
**Name:** `acts-xvii-xi`
**Config location:** `C:\Users\mhmco\AppData\Roaming\Claude\claude_desktop_config.json`
**Tools:** `get_verse`, `search_bible`, `get_commentary`, `lookup_lexicon`, `bible_health`

To use: Flask must be running locally, then restart Claude Desktop.

---

## Next Steps (in order)

### 1. Get Full Data on Render
Upload `kjv.txt`, `eb.cmti`, and `strongsplus.lexi` as assets to a GitHub Release on the actsxviixi repo. Then update the Render build command to download and load them:
```
pip install -r requirements.txt && curl -L <url>/kjv.txt -o kjv.txt && python loader.py kjv.txt && curl -L <url>/eb.cmti -o eb.cmti && python load_commentary.py && curl -L <url>/strongsplus.lexi -o strongsplus.lexi && python load_lexicon.py
```

### 2. Point Domain
In Namecheap DNS for actsxviixi.org:
- Add CNAME record: `@` → `actsxviixi.onrender.com`
- Add CNAME record: `www` → `actsxviixi.onrender.com`
Then add the custom domain in Render → Settings → Custom Domains.

### 3. Add API Key Auth
Before going fully public, add a simple API key check to protect the endpoints from abuse.

### 4. Remote MCP Connector
Once the site is live, update `mcp_server.py` to support HTTP/SSE transport so it can be added as a remote connector on claude.ai (not just Claude Desktop).

### 5. More Commentary Sources
Schema supports multiple sources. Could add:
- Matthew Henry (public domain)
- Geneva Notes (public domain)
- John Gill (public domain)

---

## Notes
- Windows Defender flagged `-WindowStyle Hidden` in PowerShell — don't use that flag
- `gh` CLI is installed but needs PATH set each session: `$env:PATH += ";C:\Program Files\GitHub CLI"`
- Git username: `treaderman` / email: `mhmcoonley@gmail.com`
- The `.cmti` and `.lexi` formats are SQLite databases — open directly with sqlite3
- Psalms in the KJV source file is spelled `Psalm` (singular) — loader normalizes it
