"""StockTwits trending source — port of my-app/src/app/services/stocktwits.service.ts.

Server-side, so no dev proxy is needed (StockTwits sends no CORS headers, which
only matters in a browser). Primary ticker source: fills spots first, RSS
supplements the gaps.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import requests

from app.models import TickerMention

log = logging.getLogger(__name__)

_URL = "https://api.stocktwits.com/api/2/trending/symbols.json"
_TIMEOUT = 10
# StockTwits returns 403 to server/cloud IPs without a browser User-Agent.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


def get_trending() -> list[TickerMention]:
    try:
        resp = requests.get(_URL, headers=_HEADERS, timeout=_TIMEOUT)
        resp.raise_for_status()
        symbols = resp.json().get("symbols", [])
    except (requests.RequestException, ValueError) as exc:
        log.warning("StockTwits fetch failed: %s", exc)
        return []

    now = datetime.now(timezone.utc)
    mentions: list[TickerMention] = []
    for s in symbols:
        score = s.get("trending_score", 0)
        mentions.append(
            TickerMention(
                ticker=s.get("symbol", ""),
                # Scale trending_score to a range comparable to Reddit counts (1-5)
                mention_count=max(1, round(score / 3)),
                total_comments=0,
                sentiment="neutral",
                latest_post_time=now,
                source="stocktwits",
            )
        )
    return mentions
