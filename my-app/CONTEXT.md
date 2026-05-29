# Harry's Risers: Social Media's Top Rising Stocks

## Project Overview
A web application that surfaces trending stock tickers from StockTwits and Reddit,
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
EventBridge (rate 30 min)
   -> CollectorFunction (Lambda) -> Reddit RSS + StockTwits + yfinance -> DynamoDB
API Gateway (HTTP API)
   -> ApiFunction (Lambda, Flask) -> DynamoDB (live) / yfinance (historical) -> JSON
Angular (GitHub Pages, thin client) -> GET /api/stocks, GET /api/historical
```

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
    stocktwits.py    # GET api.stocktwits.com/.../trending/symbols.json (needs browser UA — see below)
    prices.py        # yfinance: get_live_prices(), get_period_prices(period)
    ticker_utils.py  # PORT of frontend ticker-utils.ts (extract/score/build_mention_data)
    collector.py     # merge_mentions() + collect_live() + collect_historical(period)
    store.py         # DynamoDB boto3: get_live/put_live/put_snapshots/query_ticker_history
template.yaml        # SAM: DataTable, ApiFunction(HttpApi), CollectorFunction(ScheduleV2 30min)
Dockerfile           # public.ecr.aws/lambda/python:3.12 image for both Lambdas
requirements.txt     # flask, flask-cors, apig-wsgi, boto3, requests, feedparser, yfinance
README.md            # local run + SAM deploy instructions
tests/               # pytest: ticker scoring + merge logic (pure, no network)
```

### JSON contract (matches the Angular `Stock` interface)
`Stock.to_json()` emits:
`{ ticker, name, price, priceChange, percentChange, commentCount, sentiment, source, timestamp }`
where `timestamp` is ISO 8601. Frontend `ApiService` maps it back to a `Date`.

### Endpoints
- `GET /api/health` -> `{status:"ok"}`
- `GET /api/stocks` -> live list. Serves DynamoDB `LIVE/latest` if `DYNAMODB_TABLE`
  is set; otherwise (local dev) computes live on demand via `collector.collect_live()`.
- `GET /api/historical?period=1mo|6mo|1yr` -> period price change from yfinance
  history (real history immediately — DynamoDB accumulates *mention* history over time).

### DynamoDB schema (single table, PK/SK)
- `LIVE` / `latest` -> `{ stocks: [...], refreshedAt }` (the cached live snapshot)
- `TICKER#{sym}` / `DATE#{yyyy-mm-dd}` -> `{ price, mentionCount, source, sentiment, ttl }`
  (per-ticker daily snapshot; `ttl` expires rows after ~400 days)

### Merge logic
**Reddit RSS fills first (primary signal); StockTwits supplements any gaps; capped at 20.**
`collector.merge_mentions()` takes Reddit mentions as the first argument. StockTwits
was previously primary but was swapped because all sources showed as `stocktwits` —
Reddit discussion is the intended signal for this app.

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
curl http://localhost:8000/api/stocks
curl "http://localhost:8000/api/historical?period=1mo"
curl "http://localhost:8000/api/historical?period=6mo"
curl "http://localhost:8000/api/historical?period=1yr"

# Pretty-print
curl http://localhost:8000/api/stocks | python3 -m json.tool
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
- **StockTwits returns 403 to server/cloud IPs without a browser `User-Agent`**
  (worked before only because the dev proxy hid this). A browser UA + `Accept:
  application/json` is set in `services/stocktwits.py`. Confirmed: no-UA -> 403,
  browser-UA -> 200 (30 symbols).
- **yfinance** can be throttled on shared Lambda IPs (server-side, different from
  the old browser CORS rejection). Mitigation: collector runs on a schedule and
  caches into DynamoDB; the live hot path reads DynamoDB. Fallback option: `stooq`
  via pandas-datareader in `services/prices.py`.
- yfinance correctly drops bad/delisted symbols (e.g. `$IRA`).
- **RSS `num_comments` is always 0** — Reddit RSS feeds do not include comment
  counts. `commentCount` in the API response reflects the weighted mention score
  (weight 2 for `$TICKER`, weight 1 for bare caps) — a discussion-intensity signal,
  not a literal comment count. Real comment counts require PRAW (OAuth).
- **`hot.rss` not `new.rss`** — switched to hot feed so posts have real engagement
  behind them. New posts are unvetted noise; hot posts are ranked by upvotes +
  comment velocity.
- **Subreddits**: `wallstreetbets`, `stocks`, `investing`, `pennystocks`,
  `cryptocurrency` — all via `hot.rss?limit=100`.
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
1. **Quickest**: hit `/api/stocks` and inspect the `timestamp` field on any stock.
   If all timestamps are the same and hours old during market hours, data is stale.
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

### Data Model (`src/app/models/stock.model.ts`) — unchanged
```typescript
interface Stock {
  ticker: string; name: string; price: number; priceChange: number;
  percentChange: number; commentCount: number;
  sentiment: 'positive' | 'neutral' | 'negative';
  source: string; timestamp: Date;
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
- **Do not attempt unauthenticated Reddit JSON API** — blocked (403). Use RSS
  (current) or PRAW (when registered).
- **Reddit OAuth / PRAW is dormant** until registration clears; `praw_source.py`
  is the drop-in point. Do not re-introduce browser-side Reddit auth.
- No hardcoded tickers or company names — discovered dynamically.
- No emojis in the UI.
- Keep `backend/app/services/ticker_utils.py` in sync with the (now-trimmed)
  frontend `ticker-utils.ts` history — the scoring logic is the canonical port.
