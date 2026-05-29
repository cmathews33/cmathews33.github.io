"""AWS Lambda entry points.

  * api_handler       -> API Gateway (HTTP) via apig-wsgi (WSGI adapter; Flask is
                         WSGI, so Mangum/ASGI does not apply).
  * collector_handler -> EventBridge scheduled rule. Fetches sources, prices, and
                         writes the live snapshot + per-ticker daily history to DynamoDB.
"""
from __future__ import annotations

import logging

from apig_wsgi import make_lambda_handler

from app import app
from app.services import collector, store

logging.getLogger().setLevel(logging.INFO)
log = logging.getLogger(__name__)

# API Gateway (payload format v2.0 for HTTP API).
api_handler = make_lambda_handler(app, binary_support=True)


def collector_handler(event, context):  # noqa: ARG001 - Lambda signature
    stocks = collector.collect_live()
    store.put_live(stocks)
    store.put_snapshots(stocks)
    log.info("Collector wrote %d stocks", len(stocks))
    return {"written": len(stocks)}
