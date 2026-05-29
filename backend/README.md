# Harry's Risers — Backend

Python/Flask API that gathers trending stock tickers (Reddit RSS + StockTwits),
prices them with `yfinance`, and serves JSON to the Angular frontend. Runs on
AWS Lambda (API + scheduled collector) behind API Gateway, backed by DynamoDB.

**No API keys required.**

## Architecture

```
EventBridge (rate 30 min) -> CollectorFunction -> RSS + StockTwits + yfinance -> DynamoDB
API Gateway -> ApiFunction (Flask) -> DynamoDB (live) / yfinance (historical) -> JSON
Angular (GitHub Pages) <- GET /api/stocks, GET /api/historical
```

- **Reddit source is pluggable** (`app/sources/`): `rss` (default, no registration)
  today; `praw` later via `REDDIT_SOURCE=praw` when Reddit registration clears.
- **Ticker scoring** in `app/services/ticker_utils.py` is a direct port of
  `my-app/src/app/utils/ticker-utils.ts` — keep them in sync.

---

## Local development (first time setup)

### 1. Install Python 3.12+

The macOS system `python3` (3.7.2) is too old. Install a current version via Homebrew:

```bash
brew install python
python3 --version   # should show 3.12 or higher
```

### 2. Create the virtualenv and install dependencies

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

If `.venv/` already exists from a previous session, just re-run pip install to
make sure dependencies are current.

### 3. Start the server

> macOS AirPlay Receiver occupies port 5000 — always use port 8000.

```bash
.venv/bin/flask --app app run --port 8000
```

The server is ready when you see:
```
* Running on http://127.0.0.1:8000
```

Without `DYNAMODB_TABLE` set, `/api/stocks` computes live on demand — no AWS needed.

---

## Hitting the endpoints

Open a second terminal and use `curl`:

```bash
# Health check (instant)
curl http://localhost:8000/api/health

# Live stocks — takes ~20-30s first run (fetches RSS + StockTwits + yfinance)
curl http://localhost:8000/api/stocks

# Historical price change
curl "http://localhost:8000/api/historical?period=1mo"
curl "http://localhost:8000/api/historical?period=6mo"
curl "http://localhost:8000/api/historical?period=1yr"
```

Pretty-print the JSON output:

```bash
curl http://localhost:8000/api/stocks | python3 -m json.tool
```

---

## Running tests

```bash
.venv/bin/python -m pytest tests/ -q
```

Tests are pure (no network) — they verify ticker scoring and merge logic.

---

## Deploy to AWS (SAM)

Requires Docker, the AWS SAM CLI, and AWS credentials.

```bash
cd backend
sam build
sam deploy --guided   # first time — walks through stack name, region, params
```

Key parameters to set during `sam deploy --guided`:
- `CorsOrigins` → `https://cmathews33.github.io`
- `RedditSource` → `rss` (default)

The `ApiUrl` stack output is the value to put into
`my-app/src/environments/environment.prod.ts` → `apiBaseUrl`.

Local Lambda emulation (requires Docker + SAM CLI):
```bash
sam local start-api   # serves on http://localhost:3000
```

---

## Notes / known gotchas

- **Port 5000 blocked on macOS** — AirPlay Receiver uses it. Always run Flask on
  `--port 8000` locally.
- **macOS system Python is 3.7.2** — install Python via Homebrew (`brew install python`)
  before creating the venv.
- **StockTwits returns 403 without a browser User-Agent** — a browser UA is set
  in `app/services/stocktwits.py`. Do not remove it.
- **yfinance** can be throttled on shared Lambda IPs. The collector caches results
  in DynamoDB so the API hot path rarely calls Yahoo. Add a `stooq` fallback in
  `app/services/prices.py` if throttling becomes an issue.
- **Historical price change** is computed from real yfinance history immediately;
  DynamoDB accumulates *mention/trend* history over time (which yfinance can't give).
- **Delisted/invalid symbols** (e.g. `$IRA`) are silently dropped by yfinance.
