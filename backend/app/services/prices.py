"""Price data via yfinance — replaces Finnhub (no API key needed).

Two jobs:
  * live quotes (current price, 24h change) for the live ticker list — batched.
  * daily close history (for the one-time cold-start backfill into DynamoDB).

The historical TAB is no longer priced here: trend history is served from the
accumulated DynamoDB snapshots (see app/services/store.py + app/api.py). yfinance
is only used live (batched) and for the offline backfill.

Risk: Yahoo throttles shared cloud IPs. The collector calls the live path on a
schedule (not per request) and caches into DynamoDB, so the hot path rarely hits
Yahoo. A stooq fallback can be added here if Yahoo blocks Lambda IPs.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import yfinance as yf

log = logging.getLogger(__name__)


@dataclass
class PriceData:
    ticker: str
    name: str
    price: float
    price_change: float
    percent_change: float


def get_live_prices(tickers: list[str]) -> dict[str, PriceData]:
    """Current price + 24h change for each ticker. Unknown symbols are dropped.

    Uses a single batched `yf.Tickers()` download and reads `.fast_info` (cached,
    no extra round-trip). The company name is intentionally NOT resolved here:
    `.info` is a separate per-ticker request that adds ~N serial round-trips and
    is throttle-prone. Name falls back to the symbol; the frontend can resolve a
    display name if needed.
    """
    out: dict[str, PriceData] = {}
    if not tickers:
        return out

    try:
        data = yf.Tickers(" ".join(tickers))
    except Exception as exc:  # noqa: BLE001 - yfinance raises bare Exceptions
        log.warning("yfinance Tickers() failed: %s", exc)
        return out

    for ticker in tickers:
        try:
            info = data.tickers[ticker].fast_info
            # regular_market_price = official session price (excludes extended hours),
            # matching what Yahoo Finance shows as the day's % change.
            price = float(info.regular_market_price or info.last_price)
            prev = float(info.regular_market_previous_close or info.previous_close)
        except Exception as exc:  # noqa: BLE001
            log.debug("No live price for %s: %s", ticker, exc)
            continue
        if not price or not prev:
            continue
        change = price - prev
        pct = (change / prev) * 100 if prev else 0.0
        out[ticker] = PriceData(
            ticker=ticker,
            name=ticker,
            price=price,
            price_change=change,
            percent_change=pct,
        )
    return out


def get_daily_closes(tickers: list[str], period: str = "1y") -> dict[str, list[tuple[str, float]]]:
    """Daily (date, close) series per ticker — for the cold-start backfill.

    Batched + threaded via `yf.download`. Returns {ticker: [(yyyy-mm-dd, close)]}.
    """
    out: dict[str, list[tuple[str, float]]] = {}
    if not tickers:
        return out

    try:
        df = yf.download(
            tickers,
            period=period,
            group_by="ticker",
            auto_adjust=True,
            progress=False,
            threads=True,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("yfinance download failed: %s", exc)
        return out

    for ticker in tickers:
        try:
            closes = df["Close"] if len(tickers) == 1 else df[ticker]["Close"]
            series = closes.dropna()
            out[ticker] = [
                (idx.strftime("%Y-%m-%d"), float(val)) for idx, val in series.items()
            ]
        except Exception as exc:  # noqa: BLE001
            log.debug("No daily history for %s: %s", ticker, exc)
            continue
    return out
