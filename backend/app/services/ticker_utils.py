"""Port of my-app/src/app/utils/ticker-utils.ts.

Keep this in sync with the TypeScript original: same NON_TICKERS set, same
sentiment thresholds. Scoring is a plain **post count** — a ticker counts once
per post that mentions it, whether written as `$TICKER` or a bare uppercase
token (the old $TICKER=2 / bare-caps=1 weighting was removed). `formatSource` is
intentionally NOT ported — it stays in the frontend as a display concern.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from app.models import RedditPost, Sentiment, TickerMention

NON_TICKERS: set[str] = {
    # Reddit culture
    "DD", "OP", "TLDR", "TBH", "IMO", "IMHO", "FYI", "TIL", "LOL", "LMAO",
    "WTF", "YOLO", "FOMO", "FUD", "HODL", "APES", "MODS",
    # Roles/orgs (not tickers)
    "CEO", "CFO", "CTO", "COO", "SEC", "FDA", "FTC", "IRS", "IMF", "ECB",
    "FED", "FDIC", "DOJ", "DOE", "FCC",
    # Macro terms
    "IPO", "ETF", "GDP", "CPI", "PPI", "NFP", "APR", "APY", "ROI", "ROE",
    # Common abbreviations
    "US", "UK", "EU", "UN", "AM", "PM", "OK", "AI", "IT", "EV", "PC", "TV",
    "ATH", "ATL", "AH", "WSB",
    # Trading terms (not tickers)
    "BUY", "SELL", "HOLD", "LONG", "SHORT", "BULL", "BEAR", "PUT", "CALL",
    "EPS", "PE", "EBIT", "SPAC",
    # Common English words used in caps for emphasis
    "THE", "AND", "FOR", "NOT", "NEW", "NOW", "GET", "GOT", "BUT", "ALL",
    "TOP", "BIG", "BAD", "HOT", "OLD", "OWN", "WAY", "DAY", "GOD", "LAW",
}

# \b([A-Z]{1,5})\b preceded by $ — JS used \$([A-Z]{1,5})\b
_DOLLAR_TICKER = re.compile(r"\$([A-Z]{1,5})\b")
_BARE_TICKER = re.compile(r"\b([A-Z]{2,5})\b")


def extract_tickers(text: str) -> set[str]:
    """Return the set of ticker symbols mentioned in `text`.

    A ticker is recognised whether written as `$TICKER` or as a bare uppercase
    2-5 letter token (filtered against NON_TICKERS). There is no weighting — a
    ticker either appears in the text or it does not.
    """
    tickers: set[str] = set()

    # $TICKER — explicit cashtag.
    for m in _DOLLAR_TICKER.finditer(text):
        tickers.add(m.group(1))

    # Bare uppercase 2-5 letters, filtered against common non-ticker words.
    for m in _BARE_TICKER.finditer(text):
        t = m.group(1)
        if t not in NON_TICKERS:
            tickers.add(t)

    return tickers


def score_tickers(posts: list[RedditPost]) -> dict[str, dict]:
    """Returns {ticker: {"score": int, "posts": [RedditPost]}}.

    `score` is the number of distinct posts that mention the ticker — a plain
    post count, not a weighted intensity score.
    """
    scores: dict[str, dict] = {}

    for post in posts:
        mentioned = extract_tickers(f"{post.title} {post.selftext}")
        for ticker in mentioned:
            entry = scores.setdefault(ticker, {"score": 0, "posts": []})
            if post not in entry["posts"]:
                entry["posts"].append(post)
                entry["score"] += 1

    return scores


# How many post links to retain per ticker for the UI (the count itself is
# unaffected — this only bounds the stored/serialised list of links).
MAX_POSTS_PER_TICKER = 15


def build_mention_data(
    ticker: str, posts: list[RedditPost], score: int | None = None
) -> TickerMention:
    total_comments = sum(p.num_comments for p in posts)
    # The mention signal is a plain post count. `score` (from score_tickers) is
    # already that count; fall back to len(posts) if not provided.
    mention_count = score if score is not None else len(posts)
    avg_ratio = (
        sum(p.upvote_ratio for p in posts) / len(posts) if posts else 0.5
    )

    latest_post = (
        sorted(posts, key=lambda p: p.created_utc, reverse=True)[0] if posts else None
    )

    sentiment: Sentiment = (
        "positive" if avg_ratio >= 0.72 else "neutral" if avg_ratio >= 0.5 else "negative"
    )

    sub_counts: dict[str, int] = {}
    for p in posts:
        sub_counts[p.subreddit] = sub_counts.get(p.subreddit, 0) + 1
    source = (
        max(sub_counts.items(), key=lambda kv: kv[1])[0] if sub_counts else "unknown"
    )

    latest_time = (
        datetime.fromtimestamp(latest_post.created_utc, tz=timezone.utc)
        if latest_post and latest_post.created_utc
        else datetime.now(timezone.utc)
    )

    # Keep the most recent posts as links for the UI (newest first).
    recent_posts = sorted(posts, key=lambda p: p.created_utc, reverse=True)[
        :MAX_POSTS_PER_TICKER
    ]

    return TickerMention(
        ticker=ticker,
        mention_count=mention_count,
        total_comments=total_comments,
        sentiment=sentiment,
        latest_post_time=latest_time,
        source=source,
        posts=recent_posts,
    )
