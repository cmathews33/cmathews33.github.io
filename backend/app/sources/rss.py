"""Default Reddit source: public RSS (Atom) feeds — no auth, no registration.

Port of my-app/src/app/services/reddit.service.ts. Server-side there is no CORS
and no browser blocking, so a plain GET with a browser User-Agent works. RSS has
no upvote_ratio (defaults to 0.5 -> neutral sentiment) and no comment counts —
Reddit's Atom feeds do not include num_comments, and unauthenticated JSON API
requests are blocked (403) from server IPs. total_comments will remain 0 until
PRAW OAuth is enabled (praw_source.py drop-in, env REDDIT_SOURCE=praw).
"""
from __future__ import annotations

import calendar
import logging
from concurrent.futures import ThreadPoolExecutor

import feedparser
import requests

from app.models import RedditPost, TickerMention
from app.services.ticker_utils import build_mention_data, score_tickers

log = logging.getLogger(__name__)

SUBREDDITS = ("stocks", "valueinvesting", "investing", "securityanalysis", "stockmarket", "daytrading", "wallstreetbets")
MIN_SCORE = 1
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
_TIMEOUT = 10


class RSSRedditSource:
    def fetch_posts(self) -> list[RedditPost]:
        """All current top posts across the tracked subreddits (no time filter)."""
        return self._fetch_all(t=None)

    def fetch_posts_for_period(self, t: str) -> list[RedditPost]:
        """Top posts for a specific Reddit time period (day | week | month | year)."""
        return self._fetch_all(t=t)

    def _fetch_all(self, t: str | None) -> list[RedditPost]:
        """Concurrent fetch across all subreddits, optionally filtered by Reddit period."""
        all_posts: list[RedditPost] = []
        with ThreadPoolExecutor(max_workers=len(SUBREDDITS)) as pool:
            for posts in pool.map(lambda sub: self._fetch_subreddit(sub, t=t), SUBREDDITS):
                all_posts.extend(posts)
        return all_posts

    def get_ticker_mentions(self, limit: int = 20) -> list[TickerMention]:
        all_posts = self._fetch_all(t=None)

        scores = score_tickers(all_posts)
        ranked = sorted(
            (item for item in scores.items() if item[1]["score"] >= MIN_SCORE),
            key=lambda item: item[1]["score"],
            reverse=True,
        )[:limit]

        return [build_mention_data(ticker, data["posts"], data["score"]) for ticker, data in ranked]

    def _fetch_subreddit(self, sub: str, t: str | None = None) -> list[RedditPost]:
        params = "limit=100" + (f"&t={t}" if t else "")
        url = f"https://www.reddit.com/r/{sub}/top.rss?{params}"
        try:
            resp = requests.get(
                url, headers={"User-Agent": _USER_AGENT}, timeout=_TIMEOUT
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            log.warning("RSS fetch failed for r/%s: %s", sub, exc)
            return []

        feed = feedparser.parse(resp.content)
        posts: list[RedditPost] = []
        for entry in feed.entries:
            published = entry.get("published_parsed")
            created_utc = calendar.timegm(published) if published else 0.0
            posts.append(
                RedditPost(
                    title=(entry.get("title") or "").strip(),
                    selftext="",
                    subreddit=sub,
                    num_comments=0,
                    upvote_ratio=0.5,
                    created_utc=created_utc,
                    url=entry.get("link", ""),
                )
            )
        return posts
