from datetime import datetime, timezone

from app.models import RedditPost
from app.services.collector import merge_mentions
from app.models import TickerMention
from app.services.ticker_utils import (
    build_mention_data,
    extract_tickers,
    score_tickers,
)


def test_dollar_ticker_weight_two():
    weights = extract_tickers("buying $NVDA today")
    assert weights["NVDA"] == 2


def test_bare_ticker_weight_one_and_filtered():
    weights = extract_tickers("NVDA to the moon but not the CEO or ETF")
    assert weights["NVDA"] == 1
    assert "CEO" not in weights
    assert "ETF" not in weights


def test_dollar_not_double_counted_with_bare():
    # $NVDA (2) then bare NVDA should not add another point
    weights = extract_tickers("$NVDA and NVDA again")
    assert weights["NVDA"] == 2


def test_score_aggregates_across_posts():
    posts = [
        RedditPost(title="$TSLA ripping"),
        RedditPost(title="TSLA calls"),
    ]
    scores = score_tickers(posts)
    assert scores["TSLA"]["score"] == 3  # 2 + 1
    assert len(scores["TSLA"]["posts"]) == 2


def test_build_mention_data_sentiment_thresholds():
    pos = build_mention_data("AAA", [RedditPost(title="$AAA", upvote_ratio=0.8, subreddit="stocks")])
    neu = build_mention_data("BBB", [RedditPost(title="$BBB", upvote_ratio=0.6, subreddit="stocks")])
    neg = build_mention_data("CCC", [RedditPost(title="$CCC", upvote_ratio=0.4, subreddit="stocks")])
    assert pos.sentiment == "positive"
    assert neu.sentiment == "neutral"
    assert neg.sentiment == "negative"


def test_merge_stocktwits_first_then_reddit_gaps():
    now = datetime.now(timezone.utc)
    st = [TickerMention("AAA", 5, 0, "neutral", now, "stocktwits")]
    rd = [
        TickerMention("AAA", 2, 0, "neutral", now, "stocks"),  # dup, dropped
        TickerMention("BBB", 3, 0, "neutral", now, "stocks"),  # gap, kept
    ]
    merged = merge_mentions(st, rd, limit=20)
    assert [m.ticker for m in merged] == ["AAA", "BBB"]
    assert merged[0].source == "stocktwits"
