"""Default Reddit source: public RSS (Atom) feeds — no auth, no registration.

Port of my-app/src/app/services/reddit.service.ts. Server-side there is no CORS
and no browser blocking, so a plain GET with a browser User-Agent works. RSS has
the same limitations as before: no num_comments (defaults to 0) and no
upvote_ratio (defaults to 0.5 -> neutral sentiment).
"""
from __future__ import annotations

import calendar
import logging

import feedparser
import requests

from app.models import RedditPost, TickerMention
from app.services.ticker_utils import build_mention_data, score_tickers

log = logging.getLogger(__name__)

SUBREDDITS = ("wallstreetbets", "stocks", "investing", "pennystocks", "cryptocurrency")
MIN_SCORE = 1
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
_TIMEOUT = 10


class RSSRedditSource:
    def get_ticker_mentions(self, limit: int = 20) -> list[TickerMention]:
        all_posts: list[RedditPost] = []
        for sub in SUBREDDITS:
            all_posts.extend(self._fetch_subreddit(sub))

        scores = score_tickers(all_posts)
        ranked = sorted(
            (item for item in scores.items() if item[1]["score"] >= MIN_SCORE),
            key=lambda item: item[1]["score"],
            reverse=True,
        )[:limit]
        return [build_mention_data(ticker, data["posts"], data["score"]) for ticker, data in ranked]

    def _fetch_subreddit(self, sub: str) -> list[RedditPost]:
        url = f"https://www.reddit.com/r/{sub}/hot.rss?limit=100"
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
                )
            )
        return posts
