"""PRAW Reddit source — stub, inactive until Reddit registration clears.

When approved: set REDDIT_SOURCE=praw and provide REDDIT_CLIENT_ID /
REDDIT_CLIENT_SECRET / REDDIT_USER_AGENT env vars. Implement get_ticker_mentions
using praw to read `new`/`top` listings (which include num_comments and score,
unlike RSS), then feed posts through score_tickers / build_mention_data exactly
like RSSRedditSource. The rest of the backend and the frontend need no changes.
"""
from __future__ import annotations

from app.models import RedditPost, TickerMention

_NOT_IMPL = (
    "PRAW source not yet implemented — pending Reddit app registration. "
    "Use REDDIT_SOURCE=rss (default) until then."
)


class PrawRedditSource:
    def get_ticker_mentions(self, limit: int = 20) -> list[TickerMention]:
        raise NotImplementedError(_NOT_IMPL)

    def fetch_posts(self) -> list[RedditPost]:
        raise NotImplementedError(_NOT_IMPL)

    def fetch_posts_for_period(self, t: str) -> list[RedditPost]:  # noqa: ARG002
        raise NotImplementedError(_NOT_IMPL)
