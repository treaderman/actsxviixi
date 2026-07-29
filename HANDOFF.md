# Acts XVII:XI Project — Handoff Document
**Last updated:** July 28, 2026 (evening — lexicon entity fix deployed)

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
- `/lexicon` — Strong's Hebrew/Greek lookup by number or keyword, with
  transliterations rendering properly (`’âb`, `’ĕlâhh`, `eugenēs`) — see
  **Data Corrections** below
- `/health` — server status plus per-table row counts
- `/` — landing page; serves HTML to browsers and JSON to programmatic
  clients, chosen by `Accept` header
- MCP connector (`mcp_server.py`) registered in Claude Desktop

### What's Limited Right Now
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
- KJV text — `C:\Users\mhmco\Downloads\Bible_Reference\King_James_Bible.txt`
  (4.4MB). _This is the file earlier notes called `kjv.txt`; there is no
  `kjv.txt` in Downloads — verified 2026-07-28._
- `eb.cmti` — Expositor's Bible (100MB, in project folder)
- `strongsplus.lexi` — Strong's dictionaries (14MB, in project folder)

None of these are in the GitHub Release either — only the prebuilt `bible.db` is.
Rebuilding from scratch on a fresh machine requires re-sourcing all three.

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
| `load_lexicon.py` | Loads Strong's from `.lexi` file; decodes HTML entities + NFC-normalizes |
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

## Data Corrections

### Lexicon HTML entities — FIXED and DEPLOYED (July 28, 2026, commit `306ad10`)

**The bug.** `strip_html()` in `load_lexicon.py` decoded only a hardcoded dict of
eight *named* entities. Numeric character references were never in that dict, so
they passed straight through into the database and were served raw by the API:

| Strong's | Was stored as | Should be |
|---|---|---|
| H1 | `'a&#x0302;b` | `’âb` |
| G2104 | `eugene&#x0304;s` | `eugenēs` |
| H426 | `'e&#x0306;la&#x0302;hh` | `’ĕlâhh` |

Strong's transliterations lean heavily on combining diacritics (U+0302 circumflex,
U+0304 macron, U+0306 breve), so this hit **10,892 of 14,197** transliteration
rows (~77%), plus 494 `definition` and 3 `kjv_usage` rows. It was also broader
than first measured: definitions additionally contained *named* Greek-letter
entities (`&omega;` ×262, `&alpha;` ×238, and ~20 more).

**The fix.** `html.unescape()` — which handles named *and* numeric forms — then
`unicodedata.normalize("NFC", ...)` so `a` + U+0302 composes to the single
codepoint `â`.

Two ordering details that matter and are easy to get wrong:

- Decoding runs **after** tag stripping. Otherwise an entity-encoded angle
  bracket would be decoded into `<` and then eaten as fake markup. (This source
  happens to contain no `&lt;`/`&gt;`, but the ordering is correct regardless.)
- NFC leaves genuinely un-composable pairs alone. H7887 is the one to eyeball:
  `shı̂ylôh` keeps a dotless `ı` (U+0131) with a *separate* combining circumflex,
  because that pair has no precomposed codepoint. That is correct, not a bug.

**Why the loader was re-run instead of patching rows in place.** This is the
non-obvious part. The old dict mapped `&rsquo;` → ASCII `'`, which had *already
destroyed* the distinction between the aleph marker (`’` U+2019) and the ayin
marker (`‛` U+201B) before the data ever hit the database. An in-place `UPDATE`
over `bible.db` could recover ayin (it survived as an un-decoded entity) but
never aleph — leaving the two markers inconsistently rendered. Only a fresh parse
of `strongsplus.lexi` recovers both. Re-running is safe: `load_lexicon.py` only
`DELETE`s and re-`INSERT`s the `lexicon` table, and `schema.sql` is entirely
`CREATE ... IF NOT EXISTS`, so verses and commentaries are untouched.

**Source data quirk.** About 10 spots in `strongsplus.lexi` are *double*-escaped
(`&amp;amp;` where a literal `&` is meant). `strip_html()` has a deliberately
narrow post-unescape `&amp;` → `&` replacement for exactly this case. **Do not
generalize it into an unescape-until-stable loop** — that would corrupt any text
that legitimately spells out an entity.

**Verified.** Zero entities remain in any lexicon text column; all
transliterations are NFC; `PRAGMA integrity_check` ok; row counts unchanged
across Hebrew, Aramaic and Greek. Confirmed live on `https://actsxviixi.org`,
including a sweep of 120 rows across six search terms.

**Rollback.** The pre-fix database is still available as Release `data-v1`:
```
curl -L https://github.com/treaderman/actsxviixi/releases/download/data-v1/bible.db.gz -o bible.db.gz && gunzip -f bible.db.gz
```
Local copies (`bible.db.bak-preunescape`, `bible.db.gz`) were deleted once both
Releases were confirmed downloadable — nothing is recoverable only from disk.

> **Not a bug:** the API returns non-ASCII as JSON `\u` escapes
> (`"transliteration":"eugenēs"`). That is standard Flask behavior and valid
> JSON — every conformant client decodes it to `eugenēs`. This was left as-is
> deliberately for maximum client compatibility. Do not "fix" it by reaching for
> `ensure_ascii=False` unless there is a concrete reason.

### Rebuilding the lexicon from scratch
```
cd "C:\Users\mhmco\Projects\Bible_Commentary_App"
python load_lexicon.py
```
Expect `Loaded 14197 lexicon entries: 7999 Hebrew, 676 Aramaic, 5522 Greek.`
Requires `strongsplus.lexi` in the project folder. Publishing the result means a
new Release **and** a matching build-command change (see Next Step 1).

---

## Next Steps (in order)

### 1. Get Full Data on Render — DONE (July 28, 2026)
The prebuilt database is published as a public GitHub Release and Render
downloads it at build time rather than loading from source on every build.

**Currently deployed: `data-v2`** (`bible.db.gz`, 37,939,337 bytes compressed /
114MB expanded). `data-v1` is the *older, pre-fix* database, retained only as a
rollback point — see **Data Corrections**.

**Build Command** (set in Render dashboard → Settings)
```
pip install -r requirements.txt && curl -L https://github.com/treaderman/actsxviixi/releases/download/data-v2/bible.db.gz -o bible.db.gz && gunzip -f bible.db.gz
```

**Start Command**
```
gunicorn app:app
```

Verify with:
```
curl https://actsxviixi.org/health
```
Expect `verses_loaded: 31102`, `commentaries_loaded: 2248`, `lexicon_loaded: 14197`.

> **The database is re-downloaded on EVERY build** — Render's disk is ephemeral.
> If the referenced Release asset is deleted or renamed, **builds break**. Keep
> `data-v2` intact. Publishing a `data-v3` means updating this build command too.

_Note: `gunicorn app:app` never calls `init_db()`, so `bible.db` must exist at
the end of the build — which the command above guarantees._

_Saving any setting in the Render dashboard **auto-triggers a deploy**; there is
no need to click Manual Deploy afterward. Pushing to `master` also auto-deploys._

### 2. Point Domain — DONE (July 28, 2026)
`https://actsxviixi.org` is live with a valid certificate, and plain HTTP
301-redirects to HTTPS. `www.actsxviixi.org` finished issuing its certificate
too — verified serving over TLS with a 301 to the apex (checked 2026-07-28
evening; it had been stuck at "Certificate Pending" earlier the same day).

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

### 3. Access control — DECIDED: stay open, rate limited (July 28, 2026)
The API is **deliberately public, no key required.** It serves public-domain
text, has no write endpoints, and stores no user data, so there is nothing to
guard. A key would answer "who are you" when the only real concern is "how
much" — so the limit is on volume, not identity.

**Rate limiting** (`flask-limiter`), per client IP:

| | |
|---|---|
| Default | `60 per minute` and `2000 per hour` |
| Override | `RATE_LIMITS` env var, semicolon-separated |
| Exempt | `/` and `/health` — uptime checks always answer |
| Over limit | JSON 429 pointing at the downloadable database |

Responses carry `X-RateLimit-Limit` / `-Remaining` / `-Reset` so clients can
self-pace.

> **The IP key function is load-bearing — do not simplify it.** Render fronts
> services with Cloudflare, so `request.remote_addr` is a *proxy* address.
> Keying on it would put every caller in the world into one shared bucket and
> rate-limit them collectively. `_client_ip()` prefers `CF-Connecting-IP`, then
> the first `X-Forwarded-For` entry, then the socket address for local runs.

Storage is in-memory, which is correct for the current single gunicorn worker
but resets on restart and would not be shared across workers. If the service is
ever scaled to multiple workers or instances, move `storage_uri` to Redis.

**API key auth is still implemented and dormant**, should it ever be needed:
set `API_KEYS` (comma-separated) in the Render dashboard and callers must send
`X-API-Key: <key>` (preferred) or `?key=<key>`. Prefer the header — query
strings show up in server and proxy logs. If you do enable it, update the
landing page, which currently advertises "No key required."

### 4. Remote MCP Connector — DONE (July 28, 2026)
**Endpoint: `https://actsxviixi.org/mcp`** (Streamable HTTP, no auth).
Anyone adds it as a custom connector in Claude — no Python, no config file.
Requires a paid Claude plan; custom connectors are not on the free tier.

`server.py` is a Starlette app serving the MCP endpoint at `/mcp` and the Flask
API everywhere else, from one Render service. Start command is now:

```
uvicorn server:application --host 0.0.0.0 --port $PORT
```

`gunicorn app:app` still works as a rollback — it serves the REST API without
`/mcp`.

**Four things here are load-bearing. Each one broke the deploy when absent:**

1. **`mcp>=1.27,<2`** — mcp 2.0.0 relocated `mcp.server.fastmcp`; an unbounded
   pin resolved to it and the service exited with `ModuleNotFoundError`.
2. **Host allowlist** — the SDK blocks DNS rebinding and its defaults cover only
   localhost, so production rejected everything with `Invalid Host header`.
   `PUBLIC_HOSTS` names the real hostnames; extend via `MCP_ALLOWED_HOSTS`.
   Do not disable the check.
3. **`ACTS_API_BASE=inprocess`** — co-hosted, the tools must not call the API
   over HTTP. A blocking self-call occupies the single event loop that has to
   answer it and the server deadlocks. `server.py` sets this before importing
   `mcp_server`, which reads it at import time.
4. **Route splicing, not `Mount("/mcp")`** — Starlette's Mount matches only
   `/mcp/...`, so a bare POST to `/mcp` fell through to Flask and 404'd, and
   bare `/mcp` is exactly what clients send.

Local stdio still works unchanged: point `ACTS_API_BASE` at a real URL.

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
- `bible.db`, `bible.db.bak*`, and `bible.db.gz` are all gitignored — the database
  is distributed via GitHub Releases, never committed
- Printing lexicon data to a Windows console needs `PYTHONIOENCODING=utf-8`, or
  cp1252 raises `UnicodeEncodeError` on the diacritics
- **The Render dashboard can be driven through the Claude-in-Chrome MCP**, which
  uses the already-logged-in Chrome session — no credentials needed or entered.
  Namecheap, by contrast, is genuinely blocked by browsing policy and DNS changes
  must be made by hand.
