# Harry's Risers — Logic & Data Reference

## Architecture & Data Flow

### How data gets into DynamoDB

Two Lambda functions:

**CollectorFunction** (scheduled, no HTTP):
- Runs every **15 min during market hours** (9am–5pm ET, weekdays), **hourly off-hours**
- Fetches 5 Reddit subreddits (hot.rss, parallel) → scores/ranks tickers by mention weight → batches a yfinance price call for the top 20
- Writes two things to DynamoDB:
  1. `LIVE/latest` — the full 20-stock list + `refreshedAt` timestamp (overwrites previous)
  2. `TICKER#{sym}/DATE#{today}` — a daily snapshot per ticker (price, mentionCount, sentiment, source). `sentiment` is stored but not returned by the API — RSS always produces "neutral" so it carries no information until a real NLP signal is added

**ApiFunction** (HTTP, on-demand):
- Just reads from DynamoDB and returns JSON — does **no data fetching itself**

---

### `/api/stocks`

```json
{ "stocks": [...], "refreshedAt": "2026-05-30T14:15:00+00:00" }
```

Each stock object shape: `{ ticker, name, price, priceChange, percentChange, mentionScore, source, postTimestamp }`

- Reads the `LIVE/latest` DynamoDB item directly
- **`refreshedAt`** = timestamp of the last successful collector run. If it's >15 min old during market hours, the collector is failing or stale
- **`price`** / **`priceChange`** / **`percentChange`** = regular market session price at the time the collector ran. Uses `regular_market_price` from yfinance — extended-hours prices are excluded, so these match Yahoo Finance's official day change
- **`mentionScore`** = weighted Reddit mention score at collection time (`$TICKER`=2pts, bare caps=1pt per post). Not a comment count — RSS does not expose actual comment counts
- **`postTimestamp`** = time of the most recent Reddit post mentioning this ticker. This is a Reddit signal, not a price freshness indicator — use top-level `refreshedAt` for that
- **`sentiment`** was removed: RSS always returns `upvote_ratio=0.5` → always "neutral". The field is stored in DynamoDB for future NLP use but is not exposed in the API

---

### `/api/historical?period=1mo&ticker=AAPL`

```json
{ "ticker": "AAPL", "points": [{ "date": "2026-04-30", "price": 180.0, "mentionCount": 3, "source": "..." }] }
```

- Reads the `TICKER#AAPL/DATE#*` rows from DynamoDB, filtered to the last 30/182/365 days
- **`price`** = close price at time of that collector run (or yfinance daily close if backfilled)
- **`mentionCount`** = the weighted Reddit mention score at the time of the last collector run that day (last-write-wins per day — not a daily aggregate)
- **`source`** = `"backfill"` for seeded rows (price-only, `mentionCount=0`), or the subreddit name for live-collected rows

---

### What the data is NOT

- Not real-time prices — prices are snapshots from when the collector ran
- `mentionCount` is not a true daily total — it's the score from one sample per day
- Historical mention data only exists from deploy date forward (backfill gives you prices but `mentionCount=0` for past dates)

---

## mentionCount In Depth

### What mentionCount actually is

Each collector run scores tickers by scanning the **current hot posts** on Reddit at that moment:
- `$TICKER` in a post title → weight 2
- `BARE TICKER` in a post title → weight 1

That score is what gets written to `TICKER#{sym}/DATE#{today}` as `mentionCount`.

### The "one sample per day" problem

The collector runs ~30+ times per day. But `DATE#{today}` is the same key every run. Each write **overwrites** the previous one:

```
9:00am  collector runs → TSLA score=8  → writes TICKER#TSLA/DATE#2026-05-30 { mentionCount: 8 }
9:15am  collector runs → TSLA score=12 → writes TICKER#TSLA/DATE#2026-05-30 { mentionCount: 12 }  ← overwrites
9:30am  collector runs → TSLA score=5  → writes TICKER#TSLA/DATE#2026-05-30 { mentionCount: 5 }   ← overwrites
...
4:45pm  last run       → TSLA score=9  → writes TICKER#TSLA/DATE#2026-05-30 { mentionCount: 9 }   ← final
```

So the historical chart shows `mentionCount: 9` for that day — whatever the **last collector run captured**, not a sum or average across all runs.

### Why this matters

- A spike in mentions at 10am won't show up in history if it died down by the last run
- A ticker that went viral briefly could look unremarkable in hindsight
- The live endpoint (`/api/stocks`) is more accurate for current buzz — historical is more of a "was this ticker showing up around this date" signal, not a precise count

### To fix it properly (future work)

You'd need to either accumulate a **daily max** or **sum** across runs, rather than overwriting. That would require a different DynamoDB write strategy (e.g. `ADD mentionCount :n` via an atomic increment, or storing multiple samples and aggregating at read time).
