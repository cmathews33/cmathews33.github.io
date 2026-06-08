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
EventBridge (5 mode schedules, America/New_York) -> CollectorFunction (Lambda)
   accumulate (hourly)  -> tally distinct Reddit posts per ticker for the day
   select   (8am ET)    -> freeze top 20 from 8am yesterday–8am today as today's list
   open     (9:30am ET) -> capture each ticker's start-of-day price
   price    (intraday)  -> refresh live prices for the frozen list (Reddit data NOT refreshed)
   close    (4pm ET)    -> write one daily trend record per ticker (SOD/EOD/%chg/posts)
   -> Reddit RSS + yfinance -> DynamoDB
API Gateway (HTTP API)
   -> ApiFunction (Lambda, Flask) -> DynamoDB (live snapshot + accumulated daily records) -> JSON
Angular (GitHub Pages, thin client) -> GET /api/stocks, GET /api/historical
```

**Daily-trend model (2026-06 redesign):** the top-20 list is no longer recomputed every 15
min. Reddit posts are *accumulated continuously*; at **8am ET** the top 20 by post count from
the **preceding 24-hour window (8am yesterday → 8am today)** are *frozen* as that day's
displayed list (with links to the posts). For example, the list shown on June 4th reflects posts
from 8am June 3rd through 8am June 4th. Prices still refresh intraday for that frozen list, but
the Reddit signal is fixed for the day. At the close, one clean **daily trend record** per
ticker (start-of-day price, end-of-day price, % change, post count, post links) is written to
history — far more useful for spotting short- and long-term trends than the old per-15-min
snapshot churn. This is **not** a day-trading tool; the goal is to compile Reddit discussion +
price movement into one place over time.

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
`{ ticker, name, price, priceChange, percentChange, mentionScore, totalComments, source, postTimestamp, posts, sodPrice }`
where `postTimestamp` is ISO 8601 (time of the most recent Reddit post mentioning this ticker —
not the price capture time; use the top-level `refreshedAt` for price staleness).
`mentionScore` is now a **plain post count** — the number of distinct Reddit posts that mention
the ticker (the old `$TICKER`=2 / bare-caps=1 weighting was removed). `posts` is a list of
`{ title, url, subreddit, postedAt }` so the UI can link to the actual discussions.
`sodPrice` is the ticker's start-of-day price (captured at market open; null before then).
`sentiment` was removed: RSS always returns `upvote_ratio=0.5` → always "neutral", so the
field was dead. It remains in DynamoDB storage as a placeholder for future NLP sentiment.
`price`/`priceChange`/`percentChange` use `regular_market_price` (regular session only, no
extended-hours bleed) so they match what Yahoo Finance shows as the day's official change.

### Endpoints
- `GET /api/health` -> `{status:"ok"}`
- `GET /api/stocks` -> `{ stocks: [...], refreshedAt }`. Serves DynamoDB `LIVE/latest`
  if `DYNAMODB_TABLE` is set; otherwise (local dev) computes live on demand via
  `collector.collect_live()` (wrapping with a fresh `refreshedAt`).
- `GET /api/historical?period=day|week|month|year[&ticker=SYM]` -> **accumulated daily
  trend records** read from the DynamoDB `TICKER#/DATE#` rows (NOT a live yfinance call).
  `period` maps to a look-back window (`day`=1d, `week`=7d, `month`=30d, `year`=365d).
  The old `1mo`/`6mo`/`1yr` values are **invalid** (return 400).
  - With `ticker`: returns `{ ticker, periodPostCount, periodPriceChange, points: [{date,
    sodPrice, eodPrice, priceChange, percentChange, postCount, posts, source}] }`.
    (`price`/`mentionCount` kept as legacy aliases of `eodPrice`/`postCount`.)
  - Without `ticker`: array of that shape for **all known tickers** (from the
    `KNOWN_TICKERS` index) that have at least one record in the date window, ranked by
    `periodPostCount` descending, capped at 50. This ensures each period shows the tickers
    that were trending *in that window*, not just today's frozen live 20.
    - `periodPostCount` = total distinct-post mentions of this ticker across all records
      in the window.
    - `periodPriceChange` = percent change from first `sodPrice` to last `eodPrice` in
      the window (computed by the API, not passed from client).
  **Requires DynamoDB** — returns 503 if the table is unset. Run the backfill once so
  there is real history immediately (see below).

### DynamoDB schema (single table, PK/SK)
- `LIVE` / `latest` -> `{ stocks: [...], refreshedAt }` — the display snapshot served to the
  UI (frozen list + live prices). Written by the `open`/`price`/`close` runs.
- `SELECTION` / `current` -> `{ selectedFor, stocks: [{ticker, mentionScore, posts}] }` — the
  day's frozen top 20. Written at midnight by the `select` run; read by the price runs.
- `ACCUM#{yyyy-mm-dd}` / `TICKER#{sym}` -> `{ count, posts, urls, ttl }` — the running
  per-ticker post tally for that day (deduped by post URL). Short TTL (~3 days). Written by
  the `accumulate` run; read by `select`.
- `TICKER#{sym}` / `DATE#{yyyy-mm-dd}` -> `{ sodPrice, eodPrice, priceChange, percentChange,
  postCount, posts, source, ttl }` — one **daily trend record** per ticker (`ttl` ~400 days).
  Written once at the `close` run AND seeded (price-only) by `scripts/backfill_history.py`;
  read by `/api/historical` via `store.query_ticker_history` / `query_histories`.
- `KNOWN_TICKERS` / `all` -> DynamoDB StringSet `tickers` — the union of every ticker symbol
  that has ever appeared in a daily close record or backfill. Updated atomically by each
  `close` run and by `backfill_history.py`. Used by `/api/historical` (multi-ticker path) to
  know what to query without scanning the whole table.

### Ticker selection
**Reddit RSS is the single source.** The displayed top 20 are *frozen once per day*: posts are
accumulated through the prior day and ranked by **post count** (number of distinct posts
mentioning the ticker — no weighting), then the top 20 are frozen at midnight ET as the next
day's list. StockTwits was removed — Reddit discussion is the intended signal and StockTwits
added nothing yfinance/Reddit didn't cover.

### Cold-start backfill
Accumulated daily records only grow going forward, so a fresh table has no history.
`scripts/backfill_history.py` has two modes:

**Reddit-period discovery (default — run this first):**
For each of `day`, `week`, `month`, `year` it fetches Reddit's top posts for that window
(`?t=day|week|month|year`), discovers the top-20 trending tickers, registers them in the
`KNOWN_TICKERS` index, and seeds their yfinance price history. This ensures the historical
tab shows period-appropriate tickers, not just today's live 20:
```bash
DYNAMODB_TABLE=harrys-risers .venv/bin/python -m scripts.backfill_history
# or target a single period:
DYNAMODB_TABLE=harrys-risers .venv/bin/python -m scripts.backfill_history --period month
```

**Explicit-ticker price seeding (optional):**
```bash
DYNAMODB_TABLE=harrys-risers .venv/bin/python -m scripts.backfill_history AAPL TSLA NVDA
```

Backfilled rows are price-only: `sodPrice == eodPrice == close`, `priceChange == 0`,
`postCount == 0`, `source="backfill-{period}"`. The `close` run overwrites them day-by-day
with the real daily trend record as the app accumulates live data.

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

# 3. Seed history (discovers period-appropriate tickers from Reddit + prices from yfinance)
.venv/bin/python -m scripts.backfill_history

# 4. Start Flask with the same env, then:
curl "http://localhost:8000/api/historical?period=month"
curl "http://localhost:8000/api/historical?period=week"
curl "http://localhost:8000/api/historical?ticker=AAPL&period=year"
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
  counts. `mentionScore` in the API response is a **post count** — the number of
  distinct posts mentioning the ticker (accumulated across the day for the frozen
  list). Real comment counts require PRAW (OAuth).
- **`hot.rss` not `new.rss`** — switched to hot feed so posts have real engagement
  behind them. New posts are unvetted noise; hot posts are ranked by upvotes +
  comment velocity.
- **Subreddits**: `wallstreetbets`, `stocks`, `investing`, `pennystocks`,
  `cryptocurrency` — all via `hot.rss?limit=100`, fetched in parallel.
- **Refresh cadence**: the collector runs as five `ScheduleV2` cron schedules in
  `template.yaml`, each passing a `mode` in its `Input` (timezone `America/New_York`,
  so DST is handled): `accumulate` hourly all week, `select` at 8am ET (reads 8am
  yesterday → 8am today), `open` at 9:30am ET, `price` every 15 min 10am–4pm ET
  weekdays, `close` at 4pm ET. One Lambda image serves all modes;
  `handlers.collector_handler` dispatches on `event["mode"]`.
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

### Data Models — full 2026-06 backend contract (UPDATED 2026-06-08)

Frontend updated on branch `feature/harrys` to match the backend contract below.
Models live in `my-app/src/app/models/stock.model.ts`.

**`src/app/models/stock.model.ts`:**
```typescript
export interface RedditPostLink {
  title: string;
  url: string;        // canonical Reddit post URL — open in new tab
  subreddit: string;
  postedAt: string;   // ISO 8601
}

export interface Stock {
  ticker: string;
  name: string;
  price: number;
  priceChange: number;
  percentChange: number;
  mentionScore: number;     // plain post count (no $TICKER weighting)
  totalComments: number;    // always 0 while using RSS (no auth)
  source: string;           // most common subreddit for this ticker
  postTimestamp: Date;      // time of most recent Reddit post
  posts: RedditPostLink[];  // up to 15 links to the discussions
  sodPrice: number | null;  // start-of-day price (null before market open)
}

// /api/stocks response
export interface StocksResponse {
  stocks: Stock[];
  refreshedAt: string;  // ISO 8601 — time of last price refresh
}
```

**Historical models — add to `stock.model.ts` (or a separate `history.model.ts`):**
```typescript
export type HistoryPeriod = 'day' | 'week' | 'month' | 'year';
// OLD VALUES ('1mo' | '6mo' | '1yr') ARE NOW INVALID — the API returns 400.

export interface HistoryPoint {
  date: string;           // yyyy-mm-dd
  sodPrice: number | null;
  eodPrice: number | null;
  price: number | null;   // legacy alias for eodPrice
  priceChange: number | null;
  percentChange: number | null;
  postCount: number;
  mentionCount: number;   // legacy alias for postCount
  posts: RedditPostLink[];
  source: string;         // subreddit or "backfill-{period}"
}

export interface TickerHistory {
  ticker: string;
  periodPostCount: number;    // total distinct posts for this ticker in the window
  periodPriceChange: number | null;  // % change: first sodPrice → last eodPrice
  points: HistoryPoint[];     // daily records oldest-first
}
```

### Frontend implementation — completed 2026-06-08

All five steps completed on branch `feature/harrys`:
- `stock.model.ts` — full 2026-06 types (`RedditPostLink`, `posts`, `sodPrice`, `totalComments`, `HistoryPeriod`, `HistoryPoint`, `TickerHistory`)
- `api.service.ts` — `HistoryPeriod` is `'day'|'week'|'month'|'year'`; `TickerHistory` carries `periodPostCount`/`periodPriceChange`
- `history.service.ts` — state cache keyed on new periods
- `history.component.ts` — Day/Week/Month/Year tabs; reads `periodPriceChange` from API (not recomputed); contextual `changeLabel`; **Download CSV button** exports current filtered view
- `stock-list.component.ts` — SOD price shown inline under current price; per-row "N posts" toggle expands clickable Reddit discussion links
- `logic.component.html` — updated to reflect current architecture (5-phase collector, daily-frozen list, new API contracts)

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
