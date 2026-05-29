"""DynamoDB persistence (boto3).

Single table, PK/SK design:
  * LIVE / latest          -> the collector's most recent stock list + meta
  * TICKER#{sym} / DATE#{yyyy-mm-dd} -> daily snapshot for accumulated trend history

Reads raise if DYNAMODB_TABLE is unset, so the API falls back to computing live
in local dev (see app/api.py).
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from decimal import Decimal

import boto3

from app.models import Stock

_LIVE_PK = "LIVE"
_LIVE_SK = "latest"
# Expire per-ticker daily snapshots after ~400 days.
_SNAPSHOT_TTL_DAYS = 400


def _table():
    name = os.environ.get("DYNAMODB_TABLE")
    if not name:
        raise RuntimeError("DYNAMODB_TABLE not configured")
    return boto3.resource("dynamodb").Table(name)


def _to_decimal(obj):
    """DynamoDB rejects float; round-trip through Decimal."""
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, list):
        return [_to_decimal(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _to_decimal(v) for k, v in obj.items()}
    return obj


def _from_decimal(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, list):
        return [_from_decimal(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _from_decimal(v) for k, v in obj.items()}
    return obj


def get_live() -> list[dict] | None:
    """Return the cached live stock list (frontend JSON), or None if absent."""
    resp = _table().get_item(Key={"pk": _LIVE_PK, "sk": _LIVE_SK})
    item = resp.get("Item")
    if not item:
        return None
    return _from_decimal(item.get("stocks", []))


def put_live(stocks: list[Stock]) -> None:
    table = _table()
    now = datetime.now(timezone.utc)
    payload = [s.to_json() for s in stocks]
    table.put_item(
        Item=_to_decimal(
            {
                "pk": _LIVE_PK,
                "sk": _LIVE_SK,
                "stocks": payload,
                "refreshedAt": now.isoformat(),
            }
        )
    )


def put_snapshots(stocks: list[Stock]) -> None:
    """Write one per-ticker daily snapshot row (idempotent per ticker per day)."""
    table = _table()
    now = datetime.now(timezone.utc)
    date = now.strftime("%Y-%m-%d")
    ttl = int(now.timestamp()) + _SNAPSHOT_TTL_DAYS * 86400
    with table.batch_writer() as batch:
        for s in stocks:
            batch.put_item(
                Item=_to_decimal(
                    {
                        "pk": f"TICKER#{s.ticker}",
                        "sk": f"DATE#{date}",
                        "price": s.price,
                        "mentionCount": s.comment_count,
                        "source": s.source,
                        "sentiment": s.sentiment,
                        "ttl": ttl,
                    }
                )
            )


def query_ticker_history(ticker: str, limit: int = 400) -> list[dict]:
    resp = _table().query(
        KeyConditionExpression=(
            boto3.dynamodb.conditions.Key("pk").eq(f"TICKER#{ticker}")
        ),
        ScanIndexForward=True,
        Limit=limit,
    )
    return _from_decimal(resp.get("Items", []))
