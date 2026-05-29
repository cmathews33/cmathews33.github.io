"""Port of my-app/src/app/utils/ticker-utils.ts.

Keep this in sync with the TypeScript original: same NON_TICKERS set, same
$TICKER weight=2 / bare-caps weight=1 scoring, same sentiment thresholds.
`formatSource` is intentionally NOT ported — it stays in the frontend as a
display concern.
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


def extract_tickers(text: str) -> dict[str, int]:
    weights: dict[str, int] = {}

    # $TICKER — intentional mention, weight 2
    for m in _DOLLAR_TICKER.finditer(text):
        t = m.group(1)
        weights[t] = weights.get(t, 0) + 2

    # Bare uppercase 2-5 letters — weight 1, filtered against non-ticker words.
    # Matches TS: only add if not already present (so a $TICKER hit isn't doubled).
    for m in _BARE_TICKER.finditer(text):
        t = m.group(1)
        if t not in NON_TICKERS and t not in weights:
            weights[t] = weights.get(t, 0) + 1

    return weights


def score_tickers(posts: list[RedditPost]) -> dict[str, dict]:
    """Returns {ticker: {"score": int, "posts": [RedditPost]}}."""
    scores: dict[str, dict] = {}

    for post in posts:
        mentioned = extract_tickers(f"{post.title} {post.selftext}")
        for ticker, weight in mentioned.items():
            entry = scores.setdefault(ticker, {"score": 0, "posts": []})
            entry["score"] += weight
            if post not in entry["posts"]:
                entry["posts"].append(post)

    return scores


def build_mention_data(
    ticker: str, posts: list[RedditPost], score: int | None = None
) -> TickerMention:
    total_comments = sum(p.num_comments for p in posts)
    # Use weighted score when available (Reddit RSS has no num_comments, so
    # score — reflecting $TICKER weight=2 + bare-caps weight=1 — is the best
    # signal of discussion intensity). Fall back to post count for StockTwits.
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

    return TickerMention(
        ticker=ticker,
        mention_count=mention_count,
        total_comments=total_comments,
        sentiment=sentiment,
        latest_post_time=latest_time,
        source=source,
    )
