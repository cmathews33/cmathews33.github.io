"""HTTP API routes.

Read path strategy:
  * /api/stocks    — serves the collector's last snapshot from DynamoDB (fast,
    cheap) when DYNAMODB_TABLE is set; otherwise (local dev) computes live on
    demand. Response shape: {stocks: [...], refreshedAt: ISO8601}.
  * /api/historical — serves accumulated daily trend records from TICKER#/DATE#
    DynamoDB rows. The ticker list comes from the KNOWN_TICKERS index (all tickers
    that have ever appeared in a daily close record or backfill), filtered to those
    with at least one record in the requested date window. Requires DynamoDB.
    Periods: day (1d) | week (7d) | month (30d) | year (365d).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, make_response, request

from app.services import collector

log = logging.getLogger(__name__)

bp = Blueprint("api", __name__)

# Maps the frontend HistoryPeriod values to a look-back window in days.
PERIOD_CONFIG: dict[str, int] = {
    "day":   1,
    "week":  7,
    "month": 30,
    "year":  365,
}


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
    period = request.args.get("period", "month")
    if period not in PERIOD_CONFIG:
        return jsonify({"error": f"invalid period; expected one of {sorted(PERIOD_CONFIG)}"}), 400

    days = PERIOD_CONFIG[period]
    since = (datetime.now(timezone.utc).date() - timedelta(days=days)).isoformat()

    try:
        from app.services import store

        # Single-ticker query (unchanged).
        ticker = request.args.get("ticker")
        if ticker:
            ticker = ticker.upper()
            rows = store.query_ticker_history(ticker, since=since)
            return jsonify(_history_payload(ticker, rows))

        # Multi-ticker: use KNOWN_TICKERS index so we show all tickers that ever
        # appeared in any daily selection, not just today's live 20.
        tickers = store.get_known_tickers()
        if not tickers:
            # First-deploy fallback before backfill or any close run.
            snapshot = store.get_live() or {}
            tickers = [s["ticker"] for s in snapshot.get("stocks", [])]

        histories = store.query_histories(tickers, since=since)

        # Build payloads, filter to tickers with at least one record in the window,
        # rank by total period post count descending, cap at 50.
        payloads = [
            _history_payload(t, histories.get(t, []))
            for t in tickers
            if histories.get(t)
        ]
        payloads.sort(key=lambda p: p["periodPostCount"], reverse=True)
        return jsonify(payloads[:50])

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


def _history_payload(ticker: str, rows: list[dict],
                     period_post_count: int | None = None,
                     period_price_change: float | None = None) -> dict:
    """Shape DynamoDB daily trend records into {ticker, periodPostCount,
    periodPriceChange, points: [{date, ...}]}.

    Reads new daily-trend fields (sodPrice/eodPrice/priceChange/percentChange/
    postCount/posts) and falls back to legacy `price`/`mentionCount` fields so
    rows written before this change still render.

    `periodPostCount` and `periodPriceChange` are computed from the points when
    not supplied explicitly.
    """
    points = []
    for r in rows:
        sk = r.get("sk", "")
        date = sk[len("DATE#"):] if sk.startswith("DATE#") else r.get("date", "")
        eod = r.get("eodPrice", r.get("price"))
        sod = r.get("sodPrice", r.get("price"))
        count = r.get("postCount", r.get("mentionCount", 0))
        points.append(
            {
                "date": date,
                "sodPrice": sod,
                "eodPrice": eod,
                "price": eod,           # legacy alias
                "priceChange": r.get("priceChange"),
                "percentChange": r.get("percentChange"),
                "postCount": count,
                "mentionCount": count,  # legacy alias
                "posts": r.get("posts", []),
                "source": r.get("source", ""),
            }
        )

    # Compute period summaries if not provided.
    if period_post_count is None:
        period_post_count = sum(int(p.get("postCount") or 0) for p in points)

    if period_price_change is None and points:
        first_sod = next((p["sodPrice"] for p in points if p.get("sodPrice")), None)
        last_eod = next((p["eodPrice"] for p in reversed(points) if p.get("eodPrice")), None)
        if first_sod and last_eod and first_sod != 0:
            period_price_change = round((last_eod - first_sod) / first_sod * 100, 2)

    return {
        "ticker": ticker,
        "periodPostCount": period_post_count,
        "periodPriceChange": period_price_change,
        "points": points,
    }
