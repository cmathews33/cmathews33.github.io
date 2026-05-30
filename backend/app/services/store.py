"""DynamoDB persistence (boto3).

Single table, PK/SK design:
  * LIVE / latest          -> the collector's most recent stock list + meta
  * TICKER#{sym} / DATE#{yyyy-mm-dd} -> daily snapshot for accumulated trend history

Reads raise if DYNAMODB_TABLE is unset, so the API falls back to computing live
in local dev (see app/api.py). Set DYNAMODB_ENDPOINT to point boto3 at a local
DynamoDB (amazon/dynamodb-local) for full-flow local testing without AWS.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

from app.models import Stock

_LIVE_PK = "LIVE"
_LIVE_SK = "latest"
# Expire per-ticker daily snapshots after ~400 days.
_SNAPSHOT_TTL_DAYS = 400


def _table():
    name = os.environ.get("DYNAMODB_TABLE")
    if not name:
        raise RuntimeError("DYNAMODB_TABLE not configured")
    # DYNAMODB_ENDPOINT lets local dev target amazon/dynamodb-local.
    endpoint = os.environ.get("DYNAMODB_ENDPOINT")
    kwargs = {"endpoint_url": endpoint} if endpoint else {}
    return boto3.resource("dynamodb", **kwargs).Table(name)


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


def get_live() -> dict | None:
    """Return the cached live snapshot `{stocks, refreshedAt}`, or None if absent."""
    resp = _table().get_item(Key={"pk": _LIVE_PK, "sk": _LIVE_SK})
    item = resp.get("Item")
    if not item:
        return None
    return {
        "stocks": _from_decimal(item.get("stocks", [])),
        "refreshedAt": item.get("refreshedAt"),
    }


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


def put_history_rows(rows: list[dict]) -> None:
    """Bulk-write daily history rows (used by the cold-start backfill).

    Each row: {ticker, date(yyyy-mm-dd), price, mentionCount?, sentiment?, source?}.
    Existing rows for the same ticker/date are overwritten (so a later live
    collector run replaces a backfilled price-only row with real mention data).
    """
    table = _table()
    ttl = int(datetime.now(timezone.utc).timestamp()) + _SNAPSHOT_TTL_DAYS * 86400
    with table.batch_writer() as batch:
        for r in rows:
            batch.put_item(
                Item=_to_decimal(
                    {
                        "pk": f"TICKER#{r['ticker']}",
                        "sk": f"DATE#{r['date']}",
                        "price": r["price"],
                        "mentionCount": r.get("mentionCount", 0),
                        "source": r.get("source", "backfill"),
                        "sentiment": r.get("sentiment", "neutral"),
                        "ttl": ttl,
                    }
                )
            )


def query_ticker_history(ticker: str, since: str | None = None, limit: int = 400) -> list[dict]:
    """Daily history rows for one ticker, oldest first.

    `since` (yyyy-mm-dd) filters to rows on or after that date — ISO dates sort
    lexicographically, so the `DATE#` sort key range query is exact.
    """
    key = Key("pk").eq(f"TICKER#{ticker}")
    if since:
        key = key & Key("sk").gte(f"DATE#{since}")
    resp = _table().query(
        KeyConditionExpression=key,
        ScanIndexForward=True,
        Limit=limit,
    )
    return _from_decimal(resp.get("Items", []))


def query_histories(
    tickers: list[str], since: str | None = None, limit: int = 400
) -> dict[str, list[dict]]:
    """Daily history rows for many tickers: {ticker: [rows...]}."""
    return {t: query_ticker_history(t, since=since, limit=limit) for t in tickers}
