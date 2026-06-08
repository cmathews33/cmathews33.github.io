# Harry's Risers — Logic & Data Reference

This is **not a day-trading app.** Its purpose is to identify short- and long-term stock
trends from Reddit — compiling *which tickers Reddit is discussing, how much, with links to
the discussions*, alongside *how the stock actually moved* — into one place over time.

## Architecture & Data Flow

### How data gets into DynamoDB

Two Lambda functions.

**CollectorFunction** (scheduled, no HTTP) — one container image, five daily phases selected
by the EventBridge schedule's `Input` `mode` (see `app/handlers.collector_handler`):

| Mode | When (ET) | What it does |
|---|---|---|
| `accumulate` | hourly, all week | Fetch the Reddit hot/top feeds, map posts → tickers, and **merge into today's per-ticker tally**, deduping by post URL. |
| `select` | 12:00am daily | Read the **prior day's** accumulation, rank tickers by distinct-post count, and **freeze the top 20** (tickers + post links + count) as the day's displayed list. |
| `open` | 9:30am, weekdays | Fetch live prices for the frozen 20 and record each ticker's **start-of-day price**. |
| `price` | every 15 min, 10am–4pm weekdays | Refresh live prices for the frozen list. **Reddit data is not refreshed** — the list is fixed for the day. |
| `close` | 4:00pm, weekdays | Fetch end-of-day prices and write **one daily trend record per ticker**. |

**ApiFunction** (HTTP, on-demand) — just reads from DynamoDB and returns JSON; it does no
data fetching itself.

### Why the list is frozen daily (not recomputed every 15 min)

The old design recomputed the top 20 every 15 minutes and wrote a fresh history snapshot each
run, so both the list and its history churned constantly — a ticker that spiked at 10am could
look unremarkable by the last run, and the displayed list never sat still. Freezing the list
once per day from the prior day's accumulated post counts, and writing one clean record per
ticker per day, makes day-over-day and month-over-month trends legible.

---

### `/api/stocks`

```json
{ "stocks": [...], "refreshedAt": "2026-06-08T20:15:00+00:00" }
```

Each stock: `{ ticker, name, price, priceChange, percentChange, mentionScore, totalComments,
source, postTimestamp, posts, sodPrice }`.

- Reads the `LIVE/latest` DynamoDB item directly (the display snapshot).
- **`mentionScore`** = **post count** — the number of distinct Reddit posts mentioning the
  ticker, accumulated over the day the list was selected from. No weighting (the old
  `$TICKER`=2 / bare-caps=1 scheme was removed).
- **`posts`** = up to 15 `{ title, url, subreddit, postedAt }` links to the actual
  discussions, so the UI can let the user read them.
- **`price` / `priceChange` / `percentChange`** = current regular-session price for the frozen
  ticker, refreshed intraday by the `price` run.
- **`sodPrice`** = start-of-day price captured at the `open` run (null before market open).
- **`refreshedAt`** = timestamp of the last price refresh. **`postTimestamp`** = most recent
  post time among the ticker's posts (a Reddit signal, not price freshness).

---

### `/api/historical?period=month[&ticker=AAPL]`

Valid `period` values: `day` (1d) | `week` (7d) | `month` (30d) | `year` (365d).
The old `1mo`/`6mo`/`1yr` values are **invalid** (API returns 400).

**Single-ticker response** (`?ticker=AAPL&period=month`):
```json
{
  "ticker": "AAPL",
  "periodPostCount": 23,
  "periodPriceChange": 4.2,
  "points": [
    { "date": "2026-05-09", "sodPrice": 178.0, "eodPrice": 184.5,
      "priceChange": 6.5, "percentChange": 3.6, "postCount": 7,
      "posts": [{ "title": "...", "url": "...", "subreddit": "stocks", "postedAt": "..." }],
      "price": 184.5, "mentionCount": 7, "source": "stocks" }
  ]
}
```

**Multi-ticker response** (`?period=week` — no ticker param):
Array of the same shape, covering **all tickers in the KNOWN_TICKERS index that have at
least one daily record in the date window**, ranked by `periodPostCount` descending, capped
at 50. This means each period tab shows the tickers that were Reddit-trending *in that
window*, not just today's live 20 — which is the whole point of the historical view.

- **`periodPostCount`** = sum of `postCount` across all records in the window for this
  ticker. For backfilled rows this is 0; it becomes non-zero as the live `close` run
  accumulates real post counts.
- **`periodPriceChange`** = percent change from the first `sodPrice` in the window to the
  last `eodPrice`. Computed by the API; the frontend should **not** recompute it from
  first/last points (the API uses proper SOD/EOD anchors).
- **`sodPrice` / `eodPrice`** = start- and end-of-day price for each day's record.
- **`priceChange` / `percentChange`** = each individual day's move.
- **`posts`** = up to 15 links to the discussions that mentioned this ticker that day.
- **`price`** / **`mentionCount`** = legacy aliases for `eodPrice` / `postCount`.
- Backfilled rows are price-only: `sodPrice == eodPrice == close`, `priceChange == 0`,
  `postCount == 0`, `source == "backfill-{period}"`.

---

### How the ticker list for each period is determined

```
KNOWN_TICKERS/all  (DynamoDB StringSet)
  └── written atomically by:
        • scripts/backfill_history.py  (when it discovers tickers from Reddit's ?t=period)
        • store.put_daily_export()     (called by the daily `close` run for each ticker)
```

`/api/historical?period=week` reads `KNOWN_TICKERS/all`, queries each ticker's
`TICKER#/DATE#` records since 7 days ago, filters to those with ≥1 record in the window,
ranks by `periodPostCount`, and returns the top 50. Falls back to the LIVE snapshot if
the index doesn't exist yet (before first backfill/close run).

---

### What the data is NOT

- Not real-time prices — intraday prices are snapshots from the last `price` run; the daily
  record is anchored to the `open` and `close` captures.
- Not a day-trading signal — it is a record of Reddit interest vs. daily price movement,
  accumulated to reveal trends over days, weeks, and months.

---

## mentionScore / postCount in depth

### What it is

Through the day, each `accumulate` run scans the current Reddit hot/top posts and records,
per ticker, the **distinct posts** that mention it (`$TICKER` or a bare uppercase token,
filtered against `NON_TICKERS`). Dedup is by post URL, so the same post seen across multiple
runs counts once. At midnight the `select` run takes that day's per-ticker distinct-post count
as `mentionScore` for the frozen list, and the `close` run carries it into the daily trend
record as `postCount`.

**There is no weighting.** A ticker mentioned in 5 posts scores 5, whether the posts used
`$TICKER` or a bare uppercase token. The old `$TICKER`=2 / bare-caps=1 weighting was removed
to make the count directly interpretable.

### One record per day — by design

Each ticker has exactly one `DATE#{day}` row, written by the `close` run with the day's frozen
post count and the day's price move. Unlike the old design (which overwrote the day's row on
every 15-min run, so history showed whatever the *last* run happened to capture), the count
here reflects the **whole day's accumulation**, not a single sample.

### Backfilled rows have postCount=0

Rows seeded by `scripts/backfill_history.py` carry real yfinance prices but `postCount=0`
and `source="backfill-{period}"` — honest, since Reddit post history wasn't tracked for past
dates. The `periodPostCount` in the `/api/historical` response reflects only what the live
`close` run has accumulated since the app was deployed.

### Period-level vs day-level post counts

| Field | Where | Meaning |
|---|---|---|
| `mentionScore` | `/api/stocks` stock object | Posts accumulated for this ticker on the day it was selected |
| `postCount` | `/api/historical` history point | Posts for this ticker on that specific calendar day |
| `periodPostCount` | `/api/historical` top-level | Sum of `postCount` across all days in the query window |
