"""Price data via yfinance — replaces Finnhub (no API key needed).

Two jobs:
  * live quotes (current price, 24h change) for the live ticker list
  * period change (1mo / 6mo / 1yr) for the historical tab, computed from the
    real historical close — no waiting for snapshots to accumulate.

Risk: Yahoo throttles shared cloud IPs. The collector calls this on a schedule
(not per request) and results are cached in DynamoDB, so the hot path rarely
hits Yahoo. A stooq fallback can be added here if Yahoo blocks Lambda IPs.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import yfinance as yf

log = logging.getLogger(__name__)

# Maps the frontend HistoryPeriod values to yfinance period strings.
PERIOD_MAP = {"1mo": "1mo", "6mo": "6mo", "1yr": "1y"}


@dataclass
class PriceData:
    ticker: str
    name: str
    price: float
    price_change: float
    percent_change: float


def get_live_prices(tickers: list[str]) -> dict[str, PriceData]:
    """Current price + 24h change for each ticker. Unknown symbols are dropped."""
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
            price = float(info.last_price)
            prev = float(info.previous_close)
        except Exception as exc:  # noqa: BLE001
            log.debug("No live price for %s: %s", ticker, exc)
            continue
        if not price or not prev:
            continue
        change = price - prev
        pct = (change / prev) * 100 if prev else 0.0
        out[ticker] = PriceData(
            ticker=ticker,
            name=_safe_name(data.tickers[ticker], ticker),
            price=price,
            price_change=change,
            percent_change=pct,
        )
    return out


def get_period_prices(tickers: list[str], period: str) -> dict[str, PriceData]:
    """Period change from period-start close to latest close, per ticker."""
    out: dict[str, PriceData] = {}
    yf_period = PERIOD_MAP.get(period)
    if not yf_period or not tickers:
        return out

    for ticker in tickers:
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period=yf_period)
            if hist.empty:
                continue
            start = float(hist["Close"].iloc[0])
            latest = float(hist["Close"].iloc[-1])
        except Exception as exc:  # noqa: BLE001
            log.debug("No period history for %s: %s", ticker, exc)
            continue
        if not start or not latest:
            continue
        change = latest - start
        pct = (change / start) * 100 if start else 0.0
        out[ticker] = PriceData(
            ticker=ticker,
            name=_safe_name(t, ticker),
            price=latest,
            price_change=change,
            percent_change=pct,
        )
    return out


def _safe_name(ticker_obj, fallback: str) -> str:
    try:
        info = ticker_obj.info
        return info.get("shortName") or info.get("longName") or fallback
    except Exception:  # noqa: BLE001
        return fallback
