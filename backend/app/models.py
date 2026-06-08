"""Dataclasses mirroring the Angular `Stock` and `TickerMentionData` interfaces.

The JSON emitted by `Stock.to_json()` matches `my-app/src/app/models/stock.model.ts`
exactly so the frontend types stay unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

Sentiment = Literal["positive", "neutral", "negative"]  # used by TickerMention / ticker_utils


@dataclass
class RedditPost:
    """Mirror of `RedditPost` (my-app/src/app/models/reddit.model.ts)."""

    title: str
    selftext: str = ""
    subreddit: str = ""
    num_comments: int = 0
    upvote_ratio: float = 0.5
    created_utc: float = 0.0  # epoch seconds
    url: str = ""  # canonical Reddit post URL; used to dedupe and to link from the UI

    def to_json(self) -> dict:
        """Shape for output/storage: enough to render a clickable link in the UI."""
        posted_at = (
            datetime.fromtimestamp(self.created_utc, tz=timezone.utc).isoformat()
            if self.created_utc
            else None
        )
        return {
            "title": self.title,
            "url": self.url,
            "subreddit": self.subreddit,
            "postedAt": posted_at,
        }


@dataclass
class TickerMention:
    """Mirror of `TickerMentionData`."""

    ticker: str
    mention_count: int
    total_comments: int
    sentiment: Sentiment
    latest_post_time: datetime
    source: str
    posts: list[RedditPost] = field(default_factory=list)


@dataclass
class Stock:
    ticker: str
    name: str
    price: float
    price_change: float
    percent_change: float
    mention_score: int  # number of Reddit posts mentioning this ticker (post count)
    total_comments: int
    source: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # Links to the Reddit posts that mention this ticker (for the UI to display).
    posts: list[dict] = field(default_factory=list)
    # Start-of-day price, captured at market open; None until the open run sets it.
    sod_price: float | None = None

    def to_json(self) -> dict:
        return {
            "ticker": self.ticker,
            "name": self.name,
            "price": self.price,
            "priceChange": self.price_change,
            "percentChange": self.percent_change,
            "mentionScore": self.mention_score,
            "totalComments": self.total_comments,
            "source": self.source,
            "postTimestamp": self.timestamp.astimezone(timezone.utc).isoformat(),
            "posts": self.posts,
            "sodPrice": self.sod_price,
        }
