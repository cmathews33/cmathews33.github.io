"""Orchestration for the scheduled collector and the live (local-dev) path.

The trend pipeline runs as distinct daily phases, each a `collector` function
dispatched by `app.handlers.collector_handler` via the EventBridge `mode`:

  * accumulate -> tally distinct Reddit posts per ticker through the day
  * select     -> at midnight ET, freeze the prior day's top 20 (tickers + links)
  * open       -> at market open, capture each ticker's start-of-day price
  * price      -> intraday, refresh live prices for the frozen list (Reddit data
                  is NOT refreshed — the list is fixed for the day)
  * close      -> at market close, write one daily trend record per ticker
                  (start/end price, % change, post count, post links)

Reddit (RSS) is the single discussion signal; yfinance supplies prices. The
historical tab is served from the accumulated daily trend records in DynamoDB,
not a live price fetch — see app/services/store.py and app/api.py.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.models import Stock, TickerMention
from app.services import prices as price_service
from app.services.ticker_utils import (
    MAX_POSTS_PER_TICKER,
    build_mention_data,
    score_tickers,
)
from app.sources.base import get_reddit_source

TOP_LIMIT = 20
MIN_COUNT = 1
# Cap the deduped URL memory kept per ticker per day (bounds row size; a day's
# unique posts stay well under this, so dedupe stays exact in practice).
_MAX_URLS = 500

_ET = ZoneInfo("America/New_York")


def _today_et() -> str:
    """Calendar date in ET — the key accumulation writes to / selection displays for."""
    return datetime.now(_ET).date().isoformat()


def _ended_day_et() -> str:
    """The day that just ended in ET (robust to the midnight job firing late)."""
    return (datetime.now(_ET) - timedelta(hours=1)).date().isoformat()


# --- Phase: accumulate -------------------------------------------------------


def accumulate() -> int:
    """Merge the current Reddit posts into today's per-ticker tally (dedupe by URL)."""
    from app.services import store

    posts = get_reddit_source().fetch_posts()
    scores = score_tickers(posts)  # {ticker: {"score", "posts":[RedditPost]}}
    date = _today_et()

    existing = {r["ticker"]: r for r in store.query_accum(date)}
    updated: list[dict] = []
    for ticker, data in scores.items():
        row = existing.get(ticker, {"ticker": ticker, "count": 0, "posts": [], "urls": []})
        known = set(row.get("urls", []))
        # Oldest-first so the kept (most recent) links land at the tail.
        for post in sorted(data["posts"], key=lambda p: p.created_utc):
            if post.url and post.url not in known:
                known.add(post.url)
                row["count"] = int(row.get("count", 0)) + 1
                row["posts"].append(post.to_json())
        row["urls"] = list(known)[-_MAX_URLS:]
        row["posts"] = row["posts"][-MAX_POSTS_PER_TICKER:]
        row["ticker"] = ticker
        updated.append(row)

    store.put_accum_rows(date, updated)
    return len(updated)


# --- Phase: select -----------------------------------------------------------


def select() -> int:
    """Freeze the prior day's top-20 tickers (by post count) as today's list."""
    from app.services import store

    ended = _ended_day_et()
    selected_for = _today_et()
    rows = [r for r in store.query_accum(ended) if r.get("count", 0) >= MIN_COUNT]
    rows.sort(key=lambda r: r.get("count", 0), reverse=True)
    top = rows[:TOP_LIMIT]

    stocks = [
        {
            "ticker": r["ticker"],
            "mentionScore": int(r.get("count", 0)),
            "posts": (r.get("posts") or [])[-MAX_POSTS_PER_TICKER:],
        }
        for r in top
    ]
    store.put_selection(selected_for, stocks)
    return len(stocks)


# --- Phases: open / price (price refresh for the frozen list) ----------------


def refresh_prices(*, is_open: bool) -> int:
    """Refresh live prices for the frozen list and rewrite the display snapshot.

    `is_open` captures the current price as each ticker's start-of-day price;
    otherwise the existing start-of-day price is preserved.
    """
    from app.services import store

    selection = store.get_selection()
    if not selection or not selection.get("stocks"):
        return 0

    tickers = [s["ticker"] for s in selection["stocks"]]
    price_map = price_service.get_live_prices(tickers)

    if is_open:
        sod = {t: pd.price for t, pd in price_map.items()}
    else:
        prev = store.get_live() or {}
        sod = {s["ticker"]: s.get("sodPrice") for s in prev.get("stocks", [])}

    stocks = _build_display(selection["stocks"], price_map, sod)
    store.put_live(stocks)
    return len(stocks)


# --- Phase: close (write the daily trend record) -----------------------------


def close() -> int:
    """Capture end-of-day prices and write one daily trend record per ticker."""
    from app.services import store

    selection = store.get_selection()
    if not selection or not selection.get("stocks"):
        return 0

    tickers = [s["ticker"] for s in selection["stocks"]]
    price_map = price_service.get_live_prices(tickers)
    prev = store.get_live() or {}
    sod = {s["ticker"]: s.get("sodPrice") for s in prev.get("stocks", [])}
    date = selection.get("selectedFor") or _today_et()

    rows: list[dict] = []
    for s in selection["stocks"]:
        ticker = s["ticker"]
        pd = price_map.get(ticker)
        eod = pd.price if pd else None
        sod_p = sod.get(ticker)
        change = eod - sod_p if (eod is not None and sod_p is not None) else None
        pct = (change / sod_p * 100) if (change is not None and sod_p) else None
        rows.append(
            {
                "ticker": ticker,
                "date": date,
                "sodPrice": sod_p,
                "eodPrice": eod,
                "priceChange": change,
                "percentChange": pct,
                "postCount": int(s.get("mentionScore", 0)),
                "posts": s.get("posts", []),
                "source": _dominant_source(s.get("posts", [])),
            }
        )

    store.put_daily_export(rows)
    # Leave the display snapshot showing closing prices.
    store.put_live(_build_display(selection["stocks"], price_map, sod))
    return len(rows)


# --- Helpers -----------------------------------------------------------------


def _dominant_source(posts: list[dict]) -> str:
    """Most common subreddit among a ticker's posts (for the display `source`)."""
    counts: dict[str, int] = {}
    for p in posts:
        sub = p.get("subreddit") or ""
        if sub:
            counts[sub] = counts.get(sub, 0) + 1
    return max(counts.items(), key=lambda kv: kv[1])[0] if counts else "reddit"


def _latest_post_time(posts: list[dict]) -> datetime:
    """Most recent post time among a ticker's posts (postTimestamp), or now."""
    times = [p["postedAt"] for p in posts if p.get("postedAt")]
    if not times:
        return datetime.now(timezone.utc)
    return datetime.fromisoformat(max(times))


def _build_display(selection_stocks: list[dict], price_map, sod: dict) -> list[Stock]:
    """Merge the frozen Reddit selection with live prices into display Stocks."""
    stocks: list[Stock] = []
    for s in selection_stocks:
        ticker = s["ticker"]
        posts = s.get("posts", [])
        p = price_map.get(ticker)
        stocks.append(
            Stock(
                ticker=ticker,
                name=p.name if p else ticker,
                price=p.price if p else 0.0,
                price_change=p.price_change if p else 0.0,
                percent_change=p.percent_change if p else 0.0,
                mention_score=int(s.get("mentionScore", 0)),
                total_comments=0,
                source=_dominant_source(posts),
                timestamp=_latest_post_time(posts),
                posts=posts,
                sod_price=sod.get(ticker),
            )
        )
    return stocks


# --- Local-dev fallback (no store / no schedule) -----------------------------


def _assemble(mentions: list[TickerMention], price_map) -> list[Stock]:
    stocks: list[Stock] = []
    for m in mentions:
        p = price_map.get(m.ticker)
        stocks.append(
            Stock(
                ticker=m.ticker,
                name=p.name if p else m.ticker,
                price=p.price if p else 0.0,
                price_change=p.price_change if p else 0.0,
                percent_change=p.percent_change if p else 0.0,
                mention_score=m.mention_count,
                total_comments=m.total_comments,
                source=m.source,
                timestamp=m.latest_post_time,
                posts=[post.to_json() for post in m.posts],
            )
        )
    return stocks


def collect_live(limit: int = TOP_LIMIT) -> list[Stock]:
    """Live trending list (Reddit mentions) with current prices.

    Used by /api/stocks in local dev when no DynamoDB table is configured, and by
    the backfill script to discover tickers. Computes a fresh list on demand
    (it does NOT use the frozen daily selection).
    """
    mentions = get_reddit_source().get_ticker_mentions(limit)
    price_map = price_service.get_live_prices([m.ticker for m in mentions])
    return _assemble(mentions, price_map)
