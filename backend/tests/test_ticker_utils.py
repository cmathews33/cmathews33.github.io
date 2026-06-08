from app.models import RedditPost
from app.services.ticker_utils import (
    build_mention_data,
    extract_tickers,
    score_tickers,
)


def test_dollar_ticker_detected():
    tickers = extract_tickers("buying $NVDA today")
    assert "NVDA" in tickers


def test_bare_ticker_detected_and_filtered():
    tickers = extract_tickers("NVDA to the moon but not the CEO or ETF")
    assert "NVDA" in tickers
    assert "CEO" not in tickers
    assert "ETF" not in tickers


def test_dollar_and_bare_are_the_same_ticker():
    # $NVDA and bare NVDA collapse to a single symbol (presence, not weight).
    tickers = extract_tickers("$NVDA and NVDA again")
    assert tickers == {"NVDA"}


def test_score_counts_posts_not_weight():
    posts = [
        RedditPost(title="$TSLA ripping"),
        RedditPost(title="TSLA calls"),
    ]
    scores = score_tickers(posts)
    assert scores["TSLA"]["score"] == 2  # two posts, no weighting
    assert len(scores["TSLA"]["posts"]) == 2


def test_score_counts_each_post_once():
    # A single post mentioning a ticker twice still counts as one post.
    posts = [RedditPost(title="$TSLA TSLA TSLA to the moon")]
    scores = score_tickers(posts)
    assert scores["TSLA"]["score"] == 1


def test_build_mention_data_uses_post_count_and_keeps_links():
    posts = [
        RedditPost(title="$AAA one", subreddit="stocks", url="https://r/1", created_utc=1),
        RedditPost(title="AAA two", subreddit="stocks", url="https://r/2", created_utc=2),
    ]
    mention = build_mention_data("AAA", posts, score=len(posts))
    assert mention.mention_count == 2
    assert [p.url for p in mention.posts] == ["https://r/2", "https://r/1"]  # newest first


def test_build_mention_data_sentiment_thresholds():
    pos = build_mention_data("AAA", [RedditPost(title="$AAA", upvote_ratio=0.8, subreddit="stocks")])
    neu = build_mention_data("BBB", [RedditPost(title="$BBB", upvote_ratio=0.6, subreddit="stocks")])
    neg = build_mention_data("CCC", [RedditPost(title="$CCC", upvote_ratio=0.4, subreddit="stocks")])
    assert pos.sentiment == "positive"
    assert neu.sentiment == "neutral"
    assert neg.sentiment == "negative"
