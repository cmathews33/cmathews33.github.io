"""HTTP API routes.

Read path strategy: if a DynamoDB table is configured (DYNAMODB_TABLE env), the
live endpoint serves the collector's last snapshot from the store (fast, cheap).
Otherwise — local dev — it computes live on demand. The historical endpoint
always computes period change from yfinance (real history, no accumulation wait).
"""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

from app.services import collector

log = logging.getLogger(__name__)

bp = Blueprint("api", __name__)

VALID_PERIODS = {"1mo", "6mo", "1yr"}


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
    return jsonify(data)


@bp.get("/api/historical")
def historical():
    period = request.args.get("period", "1mo")
    if period not in VALID_PERIODS:
        return jsonify({"error": f"invalid period; expected one of {sorted(VALID_PERIODS)}"}), 400

    data = [s.to_json() for s in collector.collect_historical(period)]
    return jsonify(data)
