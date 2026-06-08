"""DynamoDB persistence (boto3).

Single table, PK/SK design:
  * LIVE / latest               -> the display snapshot (frozen list + live prices)
  * SELECTION / current         -> the day's frozen top-20 (tickers + post links),
                                   chosen at midnight from the prior day's accumulation
  * ACCUM#{yyyy-mm-dd} / TICKER#{sym} -> running per-ticker post tally for that day
                                   (deduped post links + count); short TTL
  * TICKER#{sym} / DATE#{yyyy-mm-dd}  -> one daily trend record per ticker
                                   (start/end price, % change, post count, post links)
  * KNOWN_TICKERS / all         -> growing set of every ticker ever written to a daily
                                   trend record (used by /api/historical to scope queries)

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
_SELECTION_PK = "SELECTION"
_SELECTION_SK = "current"
_KNOWN_PK = "KNOWN_TICKERS"
_KNOWN_SK = "all"
# Expire per-ticker daily trend records after ~400 days.
_SNAPSHOT_TTL_DAYS = 400
# Accumulation rows only matter until the next midnight select; expire quickly.
_ACCUM_TTL_DAYS = 3


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


# --- Daily Reddit accumulation (ACCUM#{date} / TICKER#{sym}) -----------------


def query_accum(date: str) -> list[dict]:
    """All per-ticker accumulation rows for a given day (each with a `ticker`)."""
    resp = _table().query(KeyConditionExpression=Key("pk").eq(f"ACCUM#{date}"))
    rows = _from_decimal(resp.get("Items", []))
    for r in rows:
        sk = r.get("sk", "")
        r["ticker"] = sk[len("TICKER#"):] if sk.startswith("TICKER#") else r.get("ticker", "")
        r["count"] = int(r.get("count", 0))
    return rows


def put_accum_rows(date: str, rows: list[dict]) -> None:
    """Upsert per-ticker accumulation rows for `date`.

    Each row: {ticker, count, posts:[{title,url,subreddit,postedAt}], urls:[str]}.
    """
    table = _table()
    ttl = int(datetime.now(timezone.utc).timestamp()) + _ACCUM_TTL_DAYS * 86400
    with table.batch_writer() as batch:
        for r in rows:
            batch.put_item(
                Item=_to_decimal(
                    {
                        "pk": f"ACCUM#{date}",
                        "sk": f"TICKER#{r['ticker']}",
                        "count": int(r.get("count", 0)),
                        "posts": r.get("posts", []),
                        "urls": r.get("urls", []),
                        "ttl": ttl,
                    }
                )
            )


# --- Frozen daily selection (SELECTION / current) ----------------------------


def get_selection() -> dict | None:
    """The day's frozen top-20: `{selectedFor, stocks:[{ticker, mentionScore, posts}]}`."""
    resp = _table().get_item(Key={"pk": _SELECTION_PK, "sk": _SELECTION_SK})
    item = resp.get("Item")
    if not item:
        return None
    return {
        "selectedFor": item.get("selectedFor"),
        "stocks": _from_decimal(item.get("stocks", [])),
    }


def put_selection(selected_for: str, stocks: list[dict]) -> None:
    """Freeze the day's displayed list (tickers + post links + post count)."""
    _table().put_item(
        Item=_to_decimal(
            {
                "pk": _SELECTION_PK,
                "sk": _SELECTION_SK,
                "selectedFor": selected_for,
                "stocks": stocks,
            }
        )
    )


# --- Known-tickers index (KNOWN_TICKERS / all) --------------------------------


def add_known_tickers(tickers: list[str]) -> None:
    """Atomically add `tickers` to the known-tickers index.

    Uses DynamoDB ADD (set union) so concurrent writes never corrupt the set.
    Creates the item if it doesn't exist yet.
    """
    if not tickers:
        return
    _table().update_item(
        Key={"pk": _KNOWN_PK, "sk": _KNOWN_SK},
        UpdateExpression="ADD tickers :t",
        ExpressionAttributeValues={":t": set(tickers)},
    )


def get_known_tickers() -> list[str]:
    """Return every ticker symbol that has ever been written to a daily trend record."""
    resp = _table().get_item(Key={"pk": _KNOWN_PK, "sk": _KNOWN_SK})
    item = resp.get("Item")
    if not item:
        return []
    return sorted(item.get("tickers", set()))


# --- Daily trend records (TICKER#{sym} / DATE#{date}) ------------------------


def put_daily_export(rows: list[dict]) -> None:
    """Write one daily trend record per ticker (idempotent per ticker per day).

    Each row: {ticker, date(yyyy-mm-dd), sodPrice, eodPrice, priceChange,
    percentChange, postCount, posts}.
    Also registers all tickers in the KNOWN_TICKERS index.
    """
    add_known_tickers([r["ticker"] for r in rows])
    table = _table()
    ttl = int(datetime.now(timezone.utc).timestamp()) + _SNAPSHOT_TTL_DAYS * 86400
    with table.batch_writer() as batch:
        for r in rows:
            batch.put_item(
                Item=_to_decimal(
                    {
                        "pk": f"TICKER#{r['ticker']}",
                        "sk": f"DATE#{r['date']}",
                        "sodPrice": r.get("sodPrice"),
                        "eodPrice": r.get("eodPrice"),
                        "priceChange": r.get("priceChange"),
                        "percentChange": r.get("percentChange"),
                        "postCount": r.get("postCount", 0),
                        "posts": r.get("posts", []),
                        "source": r.get("source", "reddit"),
                        "ttl": ttl,
                    }
                )
            )


def put_history_rows(rows: list[dict]) -> None:
    """Bulk-write daily trend records (used by the cold-start backfill).

    Each row: {ticker, date(yyyy-mm-dd), price}. Backfilled rows are price-only:
    sodPrice == eodPrice == close, no change, postCount=0. Existing rows for the
    same ticker/date are overwritten (so a later live `close` run replaces a
    backfilled price-only row with the real daily trend record).
    Also registers all tickers in the KNOWN_TICKERS index.
    """
    add_known_tickers(list({r["ticker"] for r in rows}))
    table = _table()
    ttl = int(datetime.now(timezone.utc).timestamp()) + _SNAPSHOT_TTL_DAYS * 86400
    with table.batch_writer() as batch:
        for r in rows:
            price = r["price"]
            batch.put_item(
                Item=_to_decimal(
                    {
                        "pk": f"TICKER#{r['ticker']}",
                        "sk": f"DATE#{r['date']}",
                        "sodPrice": price,
                        "eodPrice": price,
                        "priceChange": 0.0,
                        "percentChange": 0.0,
                        "postCount": 0,
                        "posts": [],
                        "source": r.get("source", "backfill"),
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
