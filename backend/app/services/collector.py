"""Orchestration: gather sources -> merge -> price -> assemble Stock list.

Reddit RSS fills spots first (primary signal); StockTwits adds any tickers not
already present; cap at limit.
"""
from __future__ import annotations

from app.models import Stock, TickerMention
from app.services import prices as price_service
from app.services import stocktwits
from app.sources.base import get_reddit_source

TOP_LIMIT = 20


def merge_mentions(
    reddit_mentions: list[TickerMention],
    stocktwits_mentions: list[TickerMention],
    limit: int = TOP_LIMIT,
) -> list[TickerMention]:
    seen = {m.ticker for m in reddit_mentions}
    gaps = [m for m in stocktwits_mentions if m.ticker not in seen]
    return (reddit_mentions + gaps)[:limit]


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
                comment_count=m.mention_count,
                sentiment=m.sentiment,
                source=m.source,
                timestamp=m.latest_post_time,
            )
        )
    return stocks


def collect_live(limit: int = TOP_LIMIT) -> list[Stock]:
    """Live trending list with current prices."""
    mentions = merge_mentions(
        get_reddit_source().get_ticker_mentions(limit),
        stocktwits.get_trending(),
        limit,
    )
    price_map = price_service.get_live_prices([m.ticker for m in mentions])
    return _assemble(mentions, price_map)


def collect_historical(period: str, limit: int = TOP_LIMIT) -> list[Stock]:
    """Trending list with period (1mo/6mo/1yr) price change."""
    mentions = merge_mentions(
        get_reddit_source().get_ticker_mentions(limit),
        stocktwits.get_trending(),
        limit,
    )
    price_map = price_service.get_period_prices([m.ticker for m in mentions], period)
    return _assemble(mentions, price_map)
