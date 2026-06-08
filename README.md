# Harry's Risers — Backend

Python/Flask API that gathers trending stock tickers from Reddit (RSS), prices
them with `yfinance`, and serves JSON. Runs on AWS Lambda (API + scheduled
collector) behind API Gateway, backed by DynamoDB.

**No API keys required.**

## Architecture

```
EventBridge (5 mode schedules: accumulate / select / open / price / close)
  -> CollectorFunction -> Reddit RSS + yfinance -> DynamoDB (live snapshot + daily trend records)
API Gateway -> ApiFunction (Flask) -> DynamoDB (live + accumulated daily records) -> JSON
Angular (GitHub Pages) <- GET /api/stocks, GET /api/historical
```

The top-20 list is **frozen once per day**: Reddit posts are accumulated through the day and
the top 20 by **post count** are frozen at midnight ET (with links to the posts). Prices
refresh intraday for that frozen list; at the close, one **daily trend record** per ticker
(start-of-day price, end-of-day price, % change, post count, post links) is written to history.
One Lambda image serves all five phases — `app/handlers.collector_handler` dispatches on the
schedule's `Input` `mode`.

- **Reddit source is pluggable** (`app/sources/`): `rss` (default, no registration)
  today; `praw` later via `REDDIT_SOURCE=praw` when Reddit registration clears.
  Subreddits are fetched concurrently.
- **`/api/historical` serves accumulated daily trend records** from DynamoDB (not a live
  yfinance call). Seed it once with the backfill below.
- **StockTwits was removed** — Reddit is the intended signal.
- **`mentionScore` is a plain post count** (no weighting); ticker extraction lives in
  `app/services/ticker_utils.py`.

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

# Live stocks -> {stocks, refreshedAt}. First run fetches RSS + yfinance (~10-20s).
curl http://localhost:8000/api/stocks
```

Pretty-print the JSON output:

```bash
curl http://localhost:8000/api/stocks | python3 -m json.tool
```

### Historical (needs DynamoDB)

`/api/historical` reads accumulated daily snapshots, so it needs a table. For a
full local flow, run DynamoDB Local and seed it:

```bash
docker run -d --rm -p 8001:8000 --name ddblocal amazon/dynamodb-local
export AWS_ACCESS_KEY_ID=fake AWS_SECRET_ACCESS_KEY=fake AWS_DEFAULT_REGION=us-east-1
export DYNAMODB_TABLE=harrys-risers DYNAMODB_ENDPOINT=http://localhost:8001
aws dynamodb create-table --endpoint-url http://localhost:8001 \
  --table-name harrys-risers --billing-mode PAY_PER_REQUEST \
  --attribute-definitions AttributeName=pk,AttributeType=S AttributeName=sk,AttributeType=S \
  --key-schema AttributeName=pk,KeyType=HASH AttributeName=sk,KeyType=RANGE

# Seed price history + discover Reddit-trending tickers for each time window
# (day / week / month / year — uses Reddit's ?t= sort to find who was trending)
.venv/bin/python -m scripts.backfill_history

# Or target a single period:
.venv/bin/python -m scripts.backfill_history --period month

# Restart Flask with the same env, then:
curl "http://localhost:8000/api/historical?period=month"
curl "http://localhost:8000/api/historical?ticker=AAPL&period=week"
# Valid period values: day | week | month | year  (old 1mo/6mo/1yr return 400)
```

Without a table, `/api/historical` returns 503 (and `/api/stocks` still computes
live on demand).

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
- **yfinance** can be throttled on shared Lambda IPs. The collector caches results
  in DynamoDB so the API hot path rarely calls Yahoo. Add a `stooq` fallback in
  `app/services/prices.py` if throttling becomes an issue.
- **Historical = accumulated daily trend records**, not a live price call. Real *price*
  history is seeded immediately by `scripts/backfill_history.py` (price-only); the real
  per-day record (SOD/EOD/% change/post count/post links) is written by the daily `close` run.
- **Live prices are batched** (`yf.Tickers()`); names fall back to the ticker symbol
  on the hot path (the old per-ticker `.info` call was removed for speed).
- **Delisted/invalid symbols** (e.g. `$IRA`) are silently dropped by yfinance.
