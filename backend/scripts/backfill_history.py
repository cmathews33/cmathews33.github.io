"""Seed the DynamoDB historical records so /api/historical has data immediately.

Two independent modes:

  A) Reddit-period discovery (default, no positional ticker args):
     For each period (day, week, month, year) — or a single period via --period —
     the script fetches Reddit's top posts for that time window, discovers the top-20
     trending tickers, registers them in the KNOWN_TICKERS index, then seeds their
     daily price history from yfinance.  This is the right way to populate the
     historical tab with period-appropriate tickers (not just today's live list).

  B) Explicit-ticker price-only seeding (when ticker symbols are passed):
     Fetches yfinance daily closes for those tickers and writes price-only
     TICKER#/DATE# rows.  No Reddit fetch.  Useful for adding specific tickers
     that are missing from history.

Usage (from backend/ with the venv active):

  # Backfill all four Reddit periods (recommended first-run):
  DYNAMODB_TABLE=harrys-risers .venv/bin/python -m scripts.backfill_history

  # One period only:
  DYNAMODB_TABLE=harrys-risers .venv/bin/python -m scripts.backfill_history --period month

  # Explicit tickers (price-only, no Reddit discovery):
  DYNAMODB_TABLE=harrys-risers .venv/bin/python -m scripts.backfill_history AAPL TSLA NVDA

  # Local DynamoDB:
  DYNAMODB_TABLE=harrys-risers DYNAMODB_ENDPOINT=http://localhost:8001 \\
    .venv/bin/python -m scripts.backfill_history --period week
"""
from __future__ import annotations

import argparse
import logging
import sys

from app.services import prices, store
from app.services.ticker_utils import build_mention_data, score_tickers
from app.sources.base import get_reddit_source

log = logging.getLogger(__name__)

TOP_LIMIT = 20
ALL_PERIODS = ["day", "week", "month", "year"]

# yfinance period strings that comfortably cover each Reddit window.
# Generous to ensure the date range for query_ticker_history has data.
_YF_PERIOD = {
    "day":   "5d",
    "week":  "1mo",
    "month": "3mo",
    "year":  "1y",
}


# ---------------------------------------------------------------------------
# Mode A: Reddit-period ticker discovery
# ---------------------------------------------------------------------------

def backfill_period(period: str) -> int:
    """Discover trending tickers for `period`, seed their price history.

    Returns the number of history rows written.
    """
    log.info("=== Period: %s ===", period)
    source = get_reddit_source()
    posts = source.fetch_posts_for_period(t=period)
    if not posts:
        log.warning("No posts fetched for period=%s; skipping", period)
        return 0

    scores = score_tickers(posts)
    ranked = sorted(scores.items(), key=lambda kv: kv[1]["score"], reverse=True)[:TOP_LIMIT]

    tickers = [ticker for ticker, _ in ranked]
    post_counts = {ticker: data["score"] for ticker, data in ranked}
    log.info("Top %d tickers for period=%s: %s", len(tickers), period,
             ", ".join(f"{t}({post_counts[t]})" for t in tickers))

    store.add_known_tickers(tickers)

    yf_period = _YF_PERIOD[period]
    closes = prices.get_daily_closes(tickers, period=yf_period)
    rows = [
        {"ticker": ticker, "date": date, "price": price, "source": f"backfill-{period}"}
        for ticker, series in closes.items()
        for date, price in series
    ]
    store.put_history_rows(rows)
    log.info("Wrote %d history rows for period=%s", len(rows), period)
    return len(rows)


# ---------------------------------------------------------------------------
# Mode B: Explicit-ticker price-only seeding
# ---------------------------------------------------------------------------

def backfill_explicit(tickers: list[str]) -> int:
    """Seed price history for the given tickers (no Reddit discovery)."""
    log.info("Seeding price history for %d explicit tickers: %s",
             len(tickers), ", ".join(tickers))
    store.add_known_tickers(tickers)
    closes = prices.get_daily_closes(tickers, period="1y")
    rows = [
        {"ticker": ticker, "date": date, "price": price, "source": "backfill"}
        for ticker, series in closes.items()
        for date, price in series
    ]
    store.put_history_rows(rows)
    log.info("Wrote %d history rows across %d tickers", len(rows), len(closes))
    return len(rows)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _parse(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--period",
        choices=ALL_PERIODS,
        default=None,
        help="Reddit time period to backfill (default: all four periods)",
    )
    parser.add_argument(
        "tickers",
        nargs="*",
        metavar="TICKER",
        help="Explicit ticker symbols for price-only seeding (skips Reddit discovery)",
    )
    return parser.parse_args(argv[1:])


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = _parse(argv)

    if args.tickers:
        backfill_explicit([t.upper() for t in args.tickers])
        return 0

    periods = [args.period] if args.period else ALL_PERIODS
    total = 0
    for period in periods:
        total += backfill_period(period)
    log.info("Backfill complete. Total rows written: %d", total)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
