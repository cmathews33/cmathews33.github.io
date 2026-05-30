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


def test_history_payload_extracts_date_from_sk():
    rows = [
        {"sk": "DATE#2026-05-01", "price": 10.0, "mentionCount": 3, "sentiment": "positive", "source": "stocks"},
        {"sk": "DATE#2026-05-02", "price": 11.0, "mentionCount": 0, "sentiment": "neutral", "source": "backfill"},
    ]
    payload = _history_payload("AAA", rows)
    assert payload["ticker"] == "AAA"
    assert [p["date"] for p in payload["points"]] == ["2026-05-01", "2026-05-02"]
    assert payload["points"][0]["mentionCount"] == 3


def test_stocks_serves_snapshot(client, monkeypatch):
    snap = {"stocks": [{"ticker": "AAA"}], "refreshedAt": "2026-05-30T00:00:00+00:00"}
    monkeypatch.setattr(store, "get_live", lambda: snap)
    resp = client.get("/api/stocks")
    assert resp.status_code == 200
    assert resp.get_json() == snap


def test_historical_single_ticker_uses_period_cutoff(client, monkeypatch):
    captured = {}

    def fake_query(ticker, since=None, limit=400):
        captured["ticker"] = ticker
        captured["since"] = since
        return [{"sk": "DATE#2026-05-29", "price": 5.0, "mentionCount": 1, "sentiment": "neutral", "source": "stocks"}]

    monkeypatch.setattr(store, "query_ticker_history", fake_query)
    resp = client.get("/api/historical?ticker=aaa&period=1mo")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ticker"] == "AAA"
    assert captured["ticker"] == "AAA"
    assert captured["since"] is not None  # period mapped to a cutoff date
    assert body["points"][0]["date"] == "2026-05-29"


def test_historical_all_tickers_from_snapshot(client, monkeypatch):
    monkeypatch.setattr(store, "get_live", lambda: {"stocks": [{"ticker": "AAA"}, {"ticker": "BBB"}]})
    monkeypatch.setattr(store, "query_histories", lambda tickers, since=None, limit=400: {t: [] for t in tickers})
    resp = client.get("/api/historical?period=6mo")
    assert resp.status_code == 200
    assert [item["ticker"] for item in resp.get_json()] == ["AAA", "BBB"]


def test_historical_invalid_period(client):
    resp = client.get("/api/historical?period=2yr")
    assert resp.status_code == 400


def test_historical_requires_store(client, monkeypatch):
    def boom():
        raise RuntimeError("DYNAMODB_TABLE not configured")

    monkeypatch.setattr(store, "get_live", boom)
    resp = client.get("/api/historical")
    assert resp.status_code == 503
    assert "error" in resp.get_json()
