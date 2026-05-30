"""HTTP API routes.

Read path strategy:
  * /api/stocks  — serves the collector's last snapshot from DynamoDB (fast,
    cheap) when DYNAMODB_TABLE is set; otherwise (local dev) computes live on
    demand. Response shape: {stocks: [...], refreshedAt: ISO8601}.
  * /api/historical — serves accumulated daily trend history from the per-ticker
    DynamoDB snapshots (TICKER#/DATE# rows). It does NOT call yfinance; the
    history is built up by the scheduled collector and the one-time backfill
    (see scripts/backfill_history.py). Requires DynamoDB.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, make_response, request

from app.services import collector

log = logging.getLogger(__name__)

bp = Blueprint("api", __name__)

# Maps the frontend HistoryPeriod values to a look-back window in days.
PERIOD_DAYS = {"1mo": 30, "6mo": 182, "1yr": 365}


@bp.get("/")
def index():
    html = (
        "<!doctype html><html lang='en'><head>"
        "<meta charset='utf-8'>"
        "<title>Herback Endsmelz</title>"
        "</head><body>"
        "<pre>Herback Endsmelz - API for Harry's Risers</pre>"
        "<p>Endpoints:</p><ul>"
        "<li><a href='/api/health'>/api/health</a></li>"
        "<li><a href='/api/stocks'>/api/stocks</a></li>"
        "<li><a href='/api/historical'>/api/historical</a></li>"
        "</ul></body></html>"
    )
    return make_response(html, 200, {"Content-Type": "text/html"})


@bp.get("/api/health")
def health():
    return jsonify({"status": "ok"})


@bp.get("/api/stocks")
def stocks():
    try:
        from app.services import store

        snapshot = store.get_live()
        if snapshot is not None:
            return jsonify(snapshot)
    except Exception as exc:  # noqa: BLE001 - store optional in local dev
        log.info("Store unavailable, computing live: %s", exc)

    data = [s.to_json() for s in collector.collect_live()]
    return jsonify({"stocks": data, "refreshedAt": datetime.now(timezone.utc).isoformat()})


@bp.get("/api/historical")
def historical():
    period = request.args.get("period", "1mo")
    if period not in PERIOD_DAYS:
        return jsonify({"error": f"invalid period; expected one of {sorted(PERIOD_DAYS)}"}), 400

    since = (datetime.now(timezone.utc).date() - timedelta(days=PERIOD_DAYS[period])).isoformat()

    try:
        from app.services import store

        ticker = request.args.get("ticker")
        if ticker:
            ticker = ticker.upper()
            rows = store.query_ticker_history(ticker, since=since)
            return jsonify(_history_payload(ticker, rows))

        snapshot = store.get_live() or {}
        tickers = [s["ticker"] for s in snapshot.get("stocks", [])]
        histories = store.query_histories(tickers, since=since)
        return jsonify([_history_payload(t, histories.get(t, [])) for t in tickers])
    except Exception as exc:  # noqa: BLE001
        log.warning("Historical unavailable (store required): %s", exc)
        return (
            jsonify(
                {
                    "error": "historical requires DynamoDB; set DYNAMODB_TABLE "
                    "(and DYNAMODB_ENDPOINT for local dev), then run the backfill"
                }
            ),
            503,
        )


def _history_payload(ticker: str, rows: list[dict]) -> dict:
    """Shape DynamoDB history rows into {ticker, points: [{date, ...}]}."""
    points = []
    for r in rows:
        sk = r.get("sk", "")
        date = sk[len("DATE#"):] if sk.startswith("DATE#") else r.get("date", "")
        points.append(
            {
                "date": date,
                "price": r.get("price"),
                "mentionCount": r.get("mentionCount", 0),
                "sentiment": r.get("sentiment", "neutral"),
                "source": r.get("source", ""),
            }
        )
    return {"ticker": ticker, "points": points}
