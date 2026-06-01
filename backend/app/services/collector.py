"""Orchestration: gather Reddit mentions -> price -> assemble Stock list.

Reddit (RSS) is the single discussion signal; yfinance supplies prices. The
historical trend tab is served from accumulated DynamoDB snapshots, not from a
live price fetch — see app/services/store.py and app/api.py.
"""
from __future__ import annotations

from app.models import Stock, TickerMention
from app.services import prices as price_service
from app.sources.base import get_reddit_source

TOP_LIMIT = 20


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
            )
        )
    return stocks


def collect_live(limit: int = TOP_LIMIT) -> list[Stock]:
    """Live trending list (Reddit mentions) with current prices."""
    mentions = get_reddit_source().get_ticker_mentions(limit)
    price_map = price_service.get_live_prices([m.ticker for m in mentions])
    return _assemble(mentions, price_map)
