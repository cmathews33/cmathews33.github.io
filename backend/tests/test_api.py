"""Route-level tests for the API — store and collector are stubbed so these stay
pure (no network, no DynamoDB)."""
from __future__ import annotations

import pytest

from app import app as flask_app
from app.api import _history_payload
from app.services import store


@pytest.fixture()
def client():
    flask_app.config.update(TESTING=True)
    return flask_app.test_client()


# --- _history_payload unit tests ---


def test_history_payload_extracts_date_from_sk():
    rows = [
        {"sk": "DATE#2026-05-01", "eodPrice": 10.0, "sodPrice": 9.5,
         "postCount": 3, "source": "stocks"},
        {"sk": "DATE#2026-05-02", "eodPrice": 11.0, "sodPrice": 10.0,
         "postCount": 0, "source": "backfill"},
    ]
    payload = _history_payload("AAA", rows)
    assert payload["ticker"] == "AAA"
    assert [p["date"] for p in payload["points"]] == ["2026-05-01", "2026-05-02"]
    assert payload["points"][0]["postCount"] == 3


def test_history_payload_computes_period_post_count():
    rows = [
        {"sk": "DATE#2026-06-01", "eodPrice": 10.0, "sodPrice": 9.0, "postCount": 4},
        {"sk": "DATE#2026-06-02", "eodPrice": 11.0, "sodPrice": 10.0, "postCount": 6},
    ]
    payload = _history_payload("BBB", rows)
    assert payload["periodPostCount"] == 10


def test_history_payload_computes_period_price_change():
    rows = [
        {"sk": "DATE#2026-06-01", "sodPrice": 100.0, "eodPrice": 102.0, "postCount": 1},
        {"sk": "DATE#2026-06-02", "sodPrice": 102.0, "eodPrice": 110.0, "postCount": 1},
    ]
    payload = _history_payload("CCC", rows)
    # (110 - 100) / 100 * 100 = 10.0%
    assert payload["periodPriceChange"] == 10.0


def test_history_payload_legacy_aliases():
    rows = [{"sk": "DATE#2026-06-01", "price": 50.0, "mentionCount": 2}]
    payload = _history_payload("DDD", rows)
    point = payload["points"][0]
    assert point["eodPrice"] == 50.0   # from price fallback
    assert point["postCount"] == 2     # from mentionCount fallback
    assert point["mentionCount"] == 2  # legacy alias still present


# --- /api/stocks tests ---


def test_stocks_serves_snapshot(client, monkeypatch):
    snap = {"stocks": [{"ticker": "AAA"}], "refreshedAt": "2026-05-30T00:00:00+00:00"}
    monkeypatch.setattr(store, "get_live", lambda: snap)
    resp = client.get("/api/stocks")
    assert resp.status_code == 200
    assert resp.get_json() == snap


# --- /api/historical tests ---


def test_historical_single_ticker_uses_period_cutoff(client, monkeypatch):
    captured = {}

    def fake_query(ticker, since=None, limit=400):
        captured["ticker"] = ticker
        captured["since"] = since
        return [{"sk": "DATE#2026-05-29", "eodPrice": 5.0, "sodPrice": 4.8, "postCount": 1}]

    monkeypatch.setattr(store, "query_ticker_history", fake_query)
    resp = client.get("/api/historical?ticker=aaa&period=month")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ticker"] == "AAA"
    assert captured["ticker"] == "AAA"
    assert captured["since"] is not None
    assert body["points"][0]["date"] == "2026-05-29"


def test_historical_uses_known_tickers_index(client, monkeypatch):
    monkeypatch.setattr(store, "get_known_tickers", lambda: ["AAA", "BBB"])
    monkeypatch.setattr(store, "query_histories",
                        lambda tickers, since=None, limit=400: {
                            "AAA": [{"sk": "DATE#2026-06-01", "eodPrice": 10.0, "postCount": 2}],
                            "BBB": [],  # no records in window — should be filtered out
                        })
    resp = client.get("/api/historical?period=week")
    assert resp.status_code == 200
    body = resp.get_json()
    tickers = [item["ticker"] for item in body]
    assert "AAA" in tickers
    assert "BBB" not in tickers   # filtered because no records in window


def test_historical_falls_back_to_live_snapshot_if_no_known(client, monkeypatch):
    monkeypatch.setattr(store, "get_known_tickers", lambda: [])
    monkeypatch.setattr(store, "get_live",
                        lambda: {"stocks": [{"ticker": "AAA"}, {"ticker": "BBB"}]})
    monkeypatch.setattr(store, "query_histories",
                        lambda tickers, since=None, limit=400: {
                            "AAA": [{"sk": "DATE#2026-06-01", "eodPrice": 5.0, "postCount": 1}],
                            "BBB": [{"sk": "DATE#2026-06-01", "eodPrice": 3.0, "postCount": 0}],
                        })
    resp = client.get("/api/historical?period=month")
    assert resp.status_code == 200
    assert [item["ticker"] for item in resp.get_json()] == ["AAA", "BBB"]


def test_historical_ranks_by_period_post_count(client, monkeypatch):
    monkeypatch.setattr(store, "get_known_tickers", lambda: ["LOW", "HIGH"])
    monkeypatch.setattr(store, "query_histories",
                        lambda tickers, since=None, limit=400: {
                            "LOW":  [{"sk": "DATE#2026-06-01", "eodPrice": 1.0, "postCount": 1}],
                            "HIGH": [{"sk": "DATE#2026-06-01", "eodPrice": 2.0, "postCount": 9}],
                        })
    resp = client.get("/api/historical?period=week")
    body = resp.get_json()
    assert body[0]["ticker"] == "HIGH"   # higher postCount ranked first
    assert body[0]["periodPostCount"] == 9


def test_historical_invalid_period(client):
    resp = client.get("/api/historical?period=1mo")  # old name — now invalid
    assert resp.status_code == 400


def test_historical_requires_store(client, monkeypatch):
    def boom():
        raise RuntimeError("DYNAMODB_TABLE not configured")

    monkeypatch.setattr(store, "get_known_tickers", boom)
    resp = client.get("/api/historical")
    assert resp.status_code == 503
    assert "error" in resp.get_json()
