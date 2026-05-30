# Harry's Risers: Social Media's Top Rising Stocks

## Project Overview
A web application that surfaces trending stock tickers from Reddit,
displaying them with price data and social metrics.

**As of the 2026-05 re-architecture, the app is split into a Python backend and a
thin Angular frontend.** Previously everything ran in the browser; that caused
Reddit blocking, an exposed Finnhub key, a dev proxy for CORS, and no historical
accumulation. All data-gathering now happens server-side.

- **Phase 1**: Angular UI ✅ COMPLETED
- **Phase 2**: Live data integration ✅ COMPLETED (now via backend)
- **Phase 2.5**: Historical trends tab ✅ COMPLETED (now via backend)
- **Phase 2.9 (2026-05)**: **Re-architecture to Flask backend on AWS** ✅ COMPLETED (local + infra written; AWS deploy pending)
- **Phase 3**: Auto trader bot (future)

---

## Current Architecture (post 2026-05 re-architecture)

```
EventBridge (market-hours cron: 15 min during US market hours, hourly otherwise)
   -> CollectorFunction (Lambda) -> Reddit RSS + yfinance -> DynamoDB (live snapshot + daily history)
API Gateway (HTTP API)
   -> ApiFunction (Lambda, Flask) -> DynamoDB (live snapshot + accumulated history) -> JSON
Angular (GitHub Pages, thin client) -> GET /api/stocks, GET /api/historical
```

**StockTwits was removed (2026-05).** Reddit discussion is the intended signal and
StockTwits added nothing that Reddit + yfinance don't already cover.

**Key decisions (made with the user):**
- **Backend:** Python + Flask. Lives in `backend/` at the repo root.
- **Reddit source is pluggable** (`backend/app/sources/`): `rss` is the default and
  needs **zero registration** (works today). `praw` is a stubbed drop-in for when
  Reddit registration clears (`REDDIT_SOURCE=praw`). Devvit was reconsidered and
  rejected again: it doesn't bypass registration and adds App Review + an
  HTTP-fetch domain allowlist.
- **Prices: `yfinance`** — replaced Finnhub entirely. **No API keys anywhere now.**
- **Deploy:** AWS **Lambda + API Gateway**, **DynamoDB** storage, AWS **SAM** IaC,
  **container image** Lambdas (yfinance pulls pandas/numpy, too big for a zip).
- **Frontend:** stays on **GitHub Pages**; became a thin client. All components,
  styling, and routes are unchanged.

### Backend layout (`backend/`)
```
app/
  __init__.py        # Flask app factory + flask-cors; module-level `app`
  api.py             # routes: /api/health, /api/stocks, /api/historical
  handlers.py        # api_handler (apig-wsgi) + collector_handler (EventBridge)
  models.py          # Stock / TickerMention / RedditPost dataclasses; Stock.to_json()
  sources/
    base.py          # RedditSource Protocol + get_reddit_source() factory (env REDDIT_SOURCE)
    rss.py           # RSSRedditSource (DEFAULT) — feedparser over /r/{sub}/new.rss
    praw_source.py   # stub, NotImplementedError until registration clears
  services/
    prices.py        # yfinance: get_live_prices() (batched), get_daily_closes() (backfill)
    ticker_utils.py  # PORT of frontend ticker-utils.ts (extract/score/build_mention_data)
    collector.py     # collect_live() — Reddit mentions + live prices
    store.py         # DynamoDB boto3: get_live/put_live/put_snapshots/put_history_rows/query_ticker_history/query_histories
scripts/
  backfill_history.py # one-time cold-start: seed daily price history from yfinance
template.yaml        # SAM: DataTable, ApiFunction(HttpApi), CollectorFunction(market-hours + off-hours ScheduleV2)
Dockerfile           # public.ecr.aws/lambda/python:3.12 image for both Lambdas
requirements.txt     # flask, flask-cors, apig-wsgi, boto3, requests, feedparser, yfinance
README.md            # local run + SAM deploy instructions
tests/               # pytest: ticker scoring + API route logic (pure, no network)
```

### JSON contract
Each stock object (`Stock.to_json()`) emits:
`{ ticker, name, price, priceChange, percentChange, mentionScore, source, postTimestamp }`
where `postTimestamp` is ISO 8601 (time of the most recent Reddit post mentioning this ticker —
not the price capture time; use the top-level `refreshedAt` for price staleness).
`mentionScore` is the weighted Reddit mention score (`$TICKER`=2pts, bare caps=1pt); it is
**not** a comment count — RSS does not expose comment counts.
`sentiment` was removed: RSS always returns `upvote_ratio=0.5` → always "neutral", so the
field was dead. It remains in DynamoDB storage as a placeholder for future NLP sentiment.
`price`/`priceChange`/`percentChange` use `regular_market_price` (regular session only, no
extended-hours bleed) so they match what Yahoo Finance shows as the day's official change.

### Endpoints
- `GET /api/health` -> `{status:"ok"}`
- `GET /api/stocks` -> `{ stocks: [...], refreshedAt }`. Serves DynamoDB `LIVE/latest`
  if `DYNAMODB_TABLE` is set; otherwise (local dev) computes live on demand via
  `collector.collect_live()` (wrapping with a fresh `refreshedAt`).
- `GET /api/historical?period=1mo|6mo|1yr[&ticker=SYM]` -> **accumulated daily trend
  history** read from the DynamoDB `TICKER#/DATE#` snapshots (NOT a live yfinance
  call). `period` maps to a look-back cutoff (30/182/365 days). With `ticker` it
  returns `{ ticker, points: [{date, price, mentionCount, source}] }`;
  without it, an array of that shape for each ticker in the LIVE snapshot. **Requires
  DynamoDB** — returns 503 if the table is unset. Run the backfill once so there is
  real price history immediately (see below).

### DynamoDB schema (single table, PK/SK)
- `LIVE` / `latest` -> `{ stocks: [...], refreshedAt }` (the cached live snapshot)
- `TICKER#{sym}` / `DATE#{yyyy-mm-dd}` -> `{ price, mentionCount, source, sentiment, ttl }`
  (per-ticker daily snapshot; `ttl` expires rows after ~400 days). Written by the
  collector each run AND seeded by `scripts/backfill_history.py`; read by
  `/api/historical` via `store.query_ticker_history` / `query_histories`.

### Ticker selection
**Reddit RSS is the single source**, capped at 20 by weighted mention score
(`$TICKER` weight 2, bare caps weight 1). StockTwits was removed — Reddit discussion
is the intended signal and StockTwits added nothing yfinance/Reddit didn't cover.

### Cold-start backfill
Accumulated snapshots only grow going forward, so a fresh table has almost no
history. `scripts/backfill_history.py` pulls ~1y of daily closes from yfinance
(batched via `prices.get_daily_closes`) and writes price-only `TICKER#/DATE#` rows
(`mentionCount=0`, `source="backfill"`). The scheduled collector then overwrites
*today's* row with real mention data. Run once after deploy:
```bash
DYNAMODB_TABLE=harrys-risers .venv/bin/python -m scripts.backfill_history
```

### Local development

**Prerequisites:**
- Python 3.12+ required. The macOS system `python3` is 3.7.2 (too old).
  Install via Homebrew: `brew install python`

**First-time setup:**
```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

**Start the server** (port 8000 — macOS AirPlay blocks 5000):
```bash
.venv/bin/flask --app app run --port 8000
```

**Hit the endpoints** (second terminal):
```bash
curl http://localhost:8000/api/health
curl http://localhost:8000/api/stocks        # {stocks, refreshedAt}; computes live without a table

# Pretty-print
curl http://localhost:8000/api/stocks | python3 -m json.tool
```

**Historical needs DynamoDB** (it reads accumulated snapshots, not yfinance). For a
full local flow use DynamoDB Local:
```bash
# 1. Start a local DynamoDB (Docker/Colima)
docker run -d --rm -p 8001:8000 --name ddblocal amazon/dynamodb-local

# 2. Point the app at it + create the table (once)
export AWS_ACCESS_KEY_ID=fake AWS_SECRET_ACCESS_KEY=fake AWS_DEFAULT_REGION=us-east-1
export DYNAMODB_TABLE=harrys-risers DYNAMODB_ENDPOINT=http://localhost:8001
aws dynamodb create-table --endpoint-url http://localhost:8001 \
  --table-name harrys-risers --billing-mode PAY_PER_REQUEST \
  --attribute-definitions AttributeName=pk,AttributeType=S AttributeName=sk,AttributeType=S \
  --key-schema AttributeName=pk,KeyType=HASH AttributeName=sk,KeyType=RANGE

# 3. Seed price history, then run the collector once for a live snapshot
.venv/bin/python -m scripts.backfill_history
.venv/bin/python -c "from app.services import collector, store; s=collector.collect_live(); store.put_live(s); store.put_snapshots(s)"

# 4. Start Flask with the same env, then:
curl "http://localhost:8000/api/historical?period=1mo"
curl "http://localhost:8000/api/historical?ticker=AAPL&period=6mo"
```

**Run tests:**
```bash
.venv/bin/python -m pytest tests/ -q
```

Verified locally (2026-05): `/api/stocks` returns 20 tickers with real yfinance
prices; `/api/historical?period=6mo` returns real period change; CORS preflight +
headers correct for a browser origin; 6/6 tests pass. Lambda image uses Python 3.12.

### AWS deploy
Stack `harrys-risers` deployed to `us-east-1`. See `AWSPLAN.md` for full deploy
runbook and gotchas encountered during deploy. After any `template.yaml` change,
run both `sam build && sam deploy` (not just `sam deploy`).
Put the stack's `ApiUrl` output into `my-app/src/environments/environment.prod.ts`
then rebuild and redeploy the Angular frontend (`ng build && ng deploy`).

### Gotchas discovered during development
- **macOS system `python3` is 3.7.2** — install Python via `brew install python`
  before running `python3 -m venv .venv`.
- **macOS occupies port 5000** (AirPlay Receiver) — always use `--port 8000`.
  `environment.ts` `apiBaseUrl` points at `http://localhost:8000`.
- **Reddit RSS subreddits are fetched concurrently** (ThreadPoolExecutor in
  `sources/rss.py`) — the 5 feeds are independent I/O, so this collapses ~5x
  sequential latency into roughly one request.
- **yfinance live prices are batched** via `yf.Tickers()`; `get_live_prices` no
  longer calls `.info` per ticker (that was a hidden per-ticker round-trip). The
  display `name` falls back to the ticker symbol on the hot path.
- **yfinance** can be throttled on shared Lambda IPs (server-side, different from
  the old browser CORS rejection). Mitigation: collector runs on a schedule and
  caches into DynamoDB; the live hot path reads DynamoDB. Fallback option: `stooq`
  via pandas-datareader in `services/prices.py`.
- yfinance correctly drops bad/delisted symbols (e.g. `$IRA`).
- **RSS `num_comments` is always 0** — Reddit RSS feeds do not include comment
  counts. `mentionScore` in the API response reflects the weighted mention score
  (weight 2 for `$TICKER`, weight 1 for bare caps) — a discussion-intensity signal,
  not a literal comment count. Real comment counts require PRAW (OAuth).
- **`hot.rss` not `new.rss`** — switched to hot feed so posts have real engagement
  behind them. New posts are unvetted noise; hot posts are ranked by upvotes +
  comment velocity.
- **Subreddits**: `wallstreetbets`, `stocks`, `investing`, `pennystocks`,
  `cryptocurrency` — all via `hot.rss?limit=100`, fetched in parallel.
- **Refresh cadence**: the collector runs every **15 min during US market hours**
  (weekdays) and **hourly otherwise** via two `ScheduleV2` cron schedules in
  `template.yaml` (timezone `America/New_York`, so DST is handled).
- **`src/environments/` removed from `my-app/.gitignore`** — was excluded when
  environment files held secrets (Finnhub key, Reddit client ID). No secrets remain
  there, so the files are now tracked so fresh clones can build.
- **Easter egg**: `GET /` on the API returns an HTML page reading
  "Herback Endsmelz - API for Harry's Risers" with links to all endpoints.
- **Docker Desktop not required** — Colima is a lightweight alternative:
  `brew install colima && colima start`. SAM needs `DOCKER_HOST` pointed at
  Colima's socket: `export DOCKER_HOST="unix://${HOME}/.colima/default/docker.sock"`.
  Add that export to `~/.zshrc` to persist across sessions.

### Monitoring staleness (yfinance throttling detection)
If the collector gets throttled by Yahoo Finance it fails silently — the API keeps
serving stale DynamoDB data rather than crashing. To check:
1. **Quickest**: hit `/api/stocks` and inspect the top-level `refreshedAt` field.
   If it is hours old during market hours, the collector is failing.
2. **DynamoDB console**: Explore items, filter `pk = LIVE`, `sk = latest`.
   The `refreshedAt` field is the last successful collector timestamp.
3. **CloudWatch Logs**: Log group `/aws/lambda/harrys-risers-CollectorFunction-XXXX`.
   Open the latest stream and look for `429` or request errors.

---

## Frontend (`my-app/`) — thin client

### What changed in the migration
- **New `src/app/services/api.service.ts`**: `getStocks()` + `getHistorical(period)`
  hitting `environment.apiBaseUrl`; maps the DTO `timestamp` string to `Date`.
  Also exports `HistoryPeriod`.
- **`stock.service.ts`**: now just polls `api.getStocks()` every 15 min. Public
  signals unchanged (`stocksList`, `isLoading`, `error`, `redditRefreshed`,
  `priceRefreshed`) — `redditRefreshed`/`priceRefreshed` now both reflect the one
  backend snapshot. `addStock`/`updateStock` were unused and removed.
- **`history.service.ts`**: now just calls `api.getHistorical(period)`. Public API
  unchanged (`HistoryPeriod`, `PeriodState`, `getState()`, `load()`).
- **`utils/ticker-utils.ts`**: trimmed to only `formatSource()` (display helper).
  All extract/score logic moved to the Python backend.
- **Deleted:** `services/price.service.ts`, `reddit.service.ts`,
  `stocktwits.service.ts`, `reddit-auth.service.ts`, `models/reddit.model.ts`,
  and `proxy.conf.json`.
- **`environment.ts`**: dropped `finnhubApiKey` + `redditClientId`; added
  `apiBaseUrl`. Added `environment.prod.ts` + `fileReplacements` in `angular.json`
  production config. Removed `proxyConfig` from the serve dev config.

### Build
```bash
export PATH="$HOME/.nvm/versions/node/v24.16.0/bin:$PATH"
node_modules/.bin/ng build      # clean: ~281 kB initial / ~79 kB transfer, 0 warnings
node_modules/.bin/ng serve      # dev server (needs backend running on :8000)
```

### Components (unchanged by the migration)
1. **AppComponent** (`src/app/app.ts`) — renders `<router-outlet>`.
2. **HeaderComponent** (`components/header/`) — sticky nav, RouterLink/RouterLinkActive.
3. **StockListComponent** (`components/stock-list/`) — hero + table; injects
   `StockService`; uses `stocksList/isLoading/error/redditRefreshed/priceRefreshed`
   and `formatSource`.
4. **StockCardComponent** (`components/stock-card/`) — reserved for Phase 3 detail.
5. **HistoryComponent** (`components/history/`) — period tabs; injects
   `HistoryService` (`getState`/`load`); `effect()` loads on tab switch.

### Data Model (`src/app/models/stock.model.ts`) — needs update when frontend reconnects
The backend contract changed in 2026-05; the Angular model below is stale and must be
updated before the frontend is rewired:
```typescript
// OLD (stale):
interface Stock {
  ticker: string; name: string; price: number; priceChange: number;
  percentChange: number; commentCount: number;
  sentiment: 'positive' | 'neutral' | 'negative';
  source: string; timestamp: Date;
}
// NEW contract from backend:
interface Stock {
  ticker: string; name: string; price: number; priceChange: number;
  percentChange: number; mentionScore: number;
  source: string; postTimestamp: Date;
}
```

### Styling — unchanged
- Global tokens: `src/styles.css` (CSS custom properties). App layout:
  `src/app/app-styles.css`. Component CSS per component folder.
- Color system: positive `#22c55e`/`#16a34a`/`#dcfce7`; negative
  `#ef4444`/`#dc2626`/`#fee2e2`; neutral `#94a3b8`; accent `#2563eb`;
  text `#111827`/`#6b7280`/`#9ca3af`.
- Caveat: use `&#36;{{ expr }}` for dollar signs in inline templates.

### Angular conventions (unchanged — see AGENTS.md / .claude/CLAUDE.md)
Standalone components (no explicit `standalone: true` in v20+), signals + computed,
OnPush, native control flow, `inject()`, no `ngClass`/`ngStyle`, lazy routes.

---

## Routing
`src/app/app.routes.ts` — lazy: `''` -> StockListComponent, `'historical'` ->
HistoryComponent, `'**'` -> redirect `''`. `app.ts` renders `<router-outlet>`.

---

## Phase 3: Auto Trader Bot (future)
- Decision logic on comment velocity + sentiment; broker API integration
  (Alpaca, IBKR); risk params; performance dashboard. `StockCardComponent` ready
  to wire up as the detail view.

---

## Permanent "do not" list
- **No API keys in the frontend** — everything is server-side now.
- **No dev proxy** — Flask sets CORS; deleted `proxy.conf.json`.
- **Do not re-add Finnhub** — replaced by yfinance.
- **Do not re-add StockTwits** — removed 2026-05; Reddit is the intended signal.
- **Do not attempt unauthenticated Reddit JSON API** — blocked (403). Use RSS
  (current) or PRAW (when registered).
- **Reddit OAuth / PRAW is dormant** until registration clears; `praw_source.py`
  is the drop-in point. Do not re-introduce browser-side Reddit auth.
- No hardcoded tickers or company names — discovered dynamically.
- No emojis in the UI.
- Keep `backend/app/services/ticker_utils.py` in sync with the (now-trimmed)
  frontend `ticker-utils.ts` history — the scoring logic is the canonical port.
