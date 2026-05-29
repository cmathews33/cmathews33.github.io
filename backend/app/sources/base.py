"""Pluggable Reddit source interface.

RSS ships today (zero registration). PRAW or a Devvit collector can be dropped
in later by implementing the same Protocol — nothing else in the backend changes.
"""
from __future__ import annotations

import os
from typing import Protocol

from app.models import TickerMention


class RedditSource(Protocol):
    def get_ticker_mentions(self, limit: int = 20) -> list[TickerMention]:
        """Return scored ticker mentions, highest score first, capped at `limit`."""
        ...


def get_reddit_source() -> RedditSource:
    """Factory: selects the source via REDDIT_SOURCE env var (default 'rss')."""
    kind = os.environ.get("REDDIT_SOURCE", "rss").lower()
    if kind == "praw":
        from app.sources.praw_source import PrawRedditSource

        return PrawRedditSource()
    from app.sources.rss import RSSRedditSource

    return RSSRedditSource()
