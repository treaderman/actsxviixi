# Acts XVII:XI Project — Handoff Document
**Last updated:** July 28, 2026

---

## What This Is
A free, open-source Bible study API serving KJV verses, Expositor's Bible commentary, and Strong's Hebrew/Greek lexicon as structured JSON. Designed to be queried by AI assistants (Claude) via an MCP connector.

**Live API:** https://actsxviixi.org (also reachable at https://actsxviixi.onrender.com)
**GitHub:** https://github.com/treaderman/actsxviixi

---

## Current State

### What's Working
- Flask API live at `https://actsxviixi.org` with the **full dataset**:
  66 books, 31,102 verses, 2,248 commentaries, 14,197 lexicon entries
- `/verse` — fetch single verse or range
- `/search` — full-text keyword search with OT/NT filter
- `/commentary` — Expositor's Bible notes by passage
- `/lexicon` — Strong's Hebrew/Greek lookup by number or keyword
- `/health` — server status plus per-table row counts
- MCP connector (`mcp_server.py`) registered in Claude Desktop

### What's Limited Right Now
- `www.actsxviixi.org` was still at "Certificate Pending" when this was written.
  The apex works; if www is still failing TLS, re-click **Verify** in Render.
- API key auth is implemented but switched off until `API_KEYS` is set on Render
- **Free instance spins down when idle** — the first request after a quiet period
  takes 50+ seconds. `mcp_server.py` uses a 60s timeout for this reason; any
  browser client or uptime check will see the same lag.
- MCP connector still points at `localhost:5000` by default. Now that the live
  API has full data, set `ACTS_API_BASE=https://actsxviixi.org` in the Claude
  Desktop config and local Flask is no longer needed.

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

The connector targets whatever `ACTS_API_BASE` points at (default
`http://localhost:5000`), with an optional `ACTS_API_KEY`. Once the live server
has full data, switch `ACTS_API_BASE` to `https://actsxviixi.onrender.com` and
Flask no longer needs to be running locally at all.

> **Careful — Claude Desktop can silently drop this block.** On 2026-07-28 the
> running app rewrote `claude_desktop_config.json` from its own in-memory state
> seconds after an edit, stripping `mcpServers` entirely. That is almost
> certainly how the earlier registration was lost. **Fully quit Claude Desktop
> before editing this file**, then relaunch and confirm the block survived.

---

## Next Steps (in order)

### 1. Get Full Data on Render — ONE MANUAL STEP LEFT
The prebuilt database is published as a public GitHub Release: **`data-v1`**
(`bible.db.gz`, 37MB compressed / 114MB expanded — verified to restore cleanly
with all 31,102 verses, 2,248 commentaries, and 14,197 lexicon entries).

Rather than loading from source on every build, Render just downloads it.
In the Render dashboard → Settings, set:

**Build Command**
```
pip install -r requirements.txt && curl -L https://github.com/treaderman/actsxviixi/releases/download/data-v1/bible.db.gz -o bible.db.gz && gunzip -f bible.db.gz
```

**Start Command**
```
gunicorn app:app
```

Then Manual Deploy → Clear build cache & deploy. Verify with:
```
curl https://actsxviixi.onrender.com/health
```
Expect `verses_loaded: 31102`, `commentaries_loaded: 2248`, `lexicon_loaded: 14197`.

_Note: `gunicorn app:app` never calls `init_db()`, so `bible.db` must exist at
the end of the build — which the command above guarantees._

### 2. Point Domain — DONE (July 28, 2026)
`https://actsxviixi.org` is live with a valid certificate, and plain HTTP
301-redirects to HTTPS.

DNS is **Namecheap BasicDNS** (nameservers `dns1/dns2.registrar-servers.com`),
edited under Domain List → actsxviixi.org → Manage → **Advanced DNS**:

| Type | Host | Value |
|---|---|---|
| ALIAS Record | `@` | `actsxviixi.onrender.com` |
| CNAME Record | `www` | `actsxviixi.onrender.com` |

The Namecheap parking records (a CNAME on `www` and a **URL Redirect Record** on
`@`) were deleted. The SPF `TXT` record under MAIL SETTINGS is email forwarding —
leave it alone.

> Do not use a plain `CNAME` on the apex. Namecheap rejects it, and the DNS spec
> forbids CNAME coexisting with the zone's SOA/NS records. ALIAS is preferred over
> a bare `A` record because Render's IPs can change — the ALIAS currently resolves
> to two addresses, where the documented A-record fallback (`216.24.57.1`) is one.

The Render subdomain is still enabled, so `actsxviixi.onrender.com` also works.

### 3. Add API Key Auth — CODE DONE, NOT YET ENABLED
`app.py` reads an `API_KEYS` environment variable (comma-separated list).
When it is unset or empty, auth is **disabled** and everything behaves as
before — this is why local development needs no key.

To turn it on in production, add an `API_KEYS` env var in the Render dashboard.
Clients then pass `X-API-Key: <key>` (preferred) or `?key=<key>`.
`/health` and `/` stay public so uptime checks keep working.

Prefer the header: query strings show up in server and proxy logs.

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
