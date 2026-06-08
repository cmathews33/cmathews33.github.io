"""Phase-level tests for the daily collector — store, source, and prices are
stubbed so these stay pure (no network, no DynamoDB)."""
from __future__ import annotations

from app.models import RedditPost
from app.services import collector
from app.services import prices as price_service
from app.services import store
from app.services.prices import PriceData


class _FakeSource:
    def __init__(self, posts):
        self._posts = posts

    def fetch_posts(self):
        return self._posts


def _patch_source(monkeypatch, posts):
    monkeypatch.setattr(collector, "get_reddit_source", lambda: _FakeSource(posts))


def test_accumulate_counts_distinct_posts(monkeypatch):
    posts = [
        RedditPost(title="$TSLA ripping", url="u1", created_utc=1, subreddit="stocks"),
        RedditPost(title="TSLA calls", url="u2", created_utc=2, subreddit="wallstreetbets"),
    ]
    _patch_source(monkeypatch, posts)
    monkeypatch.setattr(store, "query_accum", lambda date: [])
    captured = {}
    monkeypatch.setattr(store, "put_accum_rows", lambda date, rows: captured.update(date=date, rows=rows))

    collector.accumulate()

    rows = {r["ticker"]: r for r in captured["rows"]}
    assert rows["TSLA"]["count"] == 2
    assert sorted(rows["TSLA"]["urls"]) == ["u1", "u2"]
    assert len(rows["TSLA"]["posts"]) == 2


def test_accumulate_dedupes_against_existing(monkeypatch):
    existing = [{"ticker": "TSLA", "count": 1, "posts": [{"url": "u1"}], "urls": ["u1"]}]
    posts = [
        RedditPost(title="$TSLA again", url="u1", created_utc=1),  # dup
        RedditPost(title="$TSLA fresh", url="u3", created_utc=3),  # new
    ]
    _patch_source(monkeypatch, posts)
    monkeypatch.setattr(store, "query_accum", lambda date: existing)
    captured = {}
    monkeypatch.setattr(store, "put_accum_rows", lambda date, rows: captured.update(rows=rows))

    collector.accumulate()

    row = {r["ticker"]: r for r in captured["rows"]}["TSLA"]
    assert row["count"] == 2  # only u3 added
    assert set(row["urls"]) == {"u1", "u3"}


def test_select_freezes_top_by_count(monkeypatch):
    accum = [
        {"ticker": "AAA", "count": 5, "posts": [{"url": "a"}]},
        {"ticker": "BBB", "count": 2, "posts": [{"url": "b"}]},
        {"ticker": "CCC", "count": 0, "posts": []},  # below MIN_COUNT, dropped
    ]
    monkeypatch.setattr(store, "query_accum", lambda date: accum)
    captured = {}
    monkeypatch.setattr(store, "put_selection", lambda sel_for, stocks: captured.update(sel_for=sel_for, stocks=stocks))

    n = collector.select()

    assert n == 2
    assert [s["ticker"] for s in captured["stocks"]] == ["AAA", "BBB"]
    assert captured["stocks"][0]["mentionScore"] == 5


def test_open_captures_start_of_day_price(monkeypatch):
    selection = {"selectedFor": "2026-06-08", "stocks": [{"ticker": "AAA", "mentionScore": 3, "posts": [{"subreddit": "stocks", "url": "x", "title": "t", "postedAt": "2026-06-08T00:00:00+00:00"}]}]}
    monkeypatch.setattr(store, "get_selection", lambda: selection)
    monkeypatch.setattr(price_service, "get_live_prices", lambda tickers: {"AAA": PriceData("AAA", "Alpha", 100.0, 1.0, 1.0)})
    captured = {}
    monkeypatch.setattr(store, "put_live", lambda stocks: captured.update(stocks=stocks))

    collector.refresh_prices(is_open=True)

    stock = captured["stocks"][0]
    assert stock.sod_price == 100.0
    assert stock.mention_score == 3
    assert stock.posts and stock.posts[0]["url"] == "x"
    assert stock.source == "stocks"


def test_close_writes_daily_trend_record(monkeypatch):
    selection = {"selectedFor": "2026-06-08", "stocks": [{"ticker": "AAA", "mentionScore": 3, "posts": [{"subreddit": "stocks"}]}]}
    monkeypatch.setattr(store, "get_selection", lambda: selection)
    monkeypatch.setattr(price_service, "get_live_prices", lambda tickers: {"AAA": PriceData("AAA", "Alpha", 110.0, 0.0, 0.0)})
    monkeypatch.setattr(store, "get_live", lambda: {"stocks": [{"ticker": "AAA", "sodPrice": 100.0}]})
    monkeypatch.setattr(store, "put_live", lambda stocks: None)
    captured = {}
    monkeypatch.setattr(store, "put_daily_export", lambda rows: captured.update(rows=rows))

    collector.close()

    row = captured["rows"][0]
    assert row["sodPrice"] == 100.0
    assert row["eodPrice"] == 110.0
    assert row["priceChange"] == 10.0
    assert row["percentChange"] == 10.0
    assert row["postCount"] == 3
    assert row["date"] == "2026-06-08"
