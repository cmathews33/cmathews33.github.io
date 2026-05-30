"""One-time cold-start backfill of per-ticker daily PRICE history.

Accumulated trend snapshots only exist going forward (the collector writes one
row per ticker per run). Without seeding, /api/historical returns almost nothing
until days have passed. This pulls real daily closes from yfinance and writes
TICKER#/DATE# rows so the historical endpoint has a real price line immediately.
Mention counts/sentiment accumulate live from the scheduled collector; backfilled
past dates carry mentionCount=0 and source="backfill" (honest — we weren't
tracking mentions then).

Usage (from the backend/ directory, with the venv active):

  DYNAMODB_TABLE=harrys-risers \\
    .venv/bin/python -m scripts.backfill_history

  # explicit tickers and a local DynamoDB:
  DYNAMODB_TABLE=harrys-risers DYNAMODB_ENDPOINT=http://localhost:8001 \\
    .venv/bin/python -m scripts.backfill_history AAPL TSLA NVDA

With no ticker args, it backfills whatever is in the current LIVE snapshot
(falling back to a fresh live collection if the snapshot is empty).
"""
from __future__ import annotations

import logging
import sys

from app.services import collector, prices, store

log = logging.getLogger(__name__)


def _resolve_tickers(argv: list[str]) -> list[str]:
    explicit = [t.upper() for t in argv[1:]]
    if explicit:
        return explicit
    snapshot = store.get_live() or {}
    tickers = [s["ticker"] for s in snapshot.get("stocks", [])]
    if tickers:
        return tickers
    log.info("LIVE snapshot empty; collecting live to discover tickers")
    return [s.ticker for s in collector.collect_live()]


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO)
    tickers = _resolve_tickers(argv)
    if not tickers:
        log.warning("No tickers to backfill")
        return 1

    log.info("Backfilling daily history for %d tickers: %s", len(tickers), ", ".join(tickers))
    closes = prices.get_daily_closes(tickers, period="1y")

    rows = [
        {
            "ticker": ticker,
            "date": date,
            "price": price,
            "mentionCount": 0,
            "sentiment": "neutral",
            "source": "backfill",
        }
        for ticker, series in closes.items()
        for date, price in series
    ]
    store.put_history_rows(rows)
    log.info("Wrote %d history rows across %d tickers", len(rows), len(closes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
