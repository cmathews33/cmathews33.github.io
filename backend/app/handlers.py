"""AWS Lambda entry points.

  * api_handler       -> API Gateway (HTTP) via apig-wsgi (WSGI adapter; Flask is
                         WSGI, so Mangum/ASGI does not apply).
  * collector_handler -> EventBridge scheduled rules. The schedule's `Input` JSON
                         carries a `mode` selecting the daily phase to run; see
                         app/services/collector.py for what each phase does.
"""
from __future__ import annotations

import logging

from apig_wsgi import make_lambda_handler

from app import app
from app.services import collector

logging.getLogger().setLevel(logging.INFO)
log = logging.getLogger(__name__)

# API Gateway (payload format v2.0 for HTTP API).
api_handler = make_lambda_handler(app, binary_support=True)

# Maps the EventBridge `mode` to the collector phase it runs.
_MODES = {
    "accumulate": collector.accumulate,
    "select": collector.select,
    "open": lambda: collector.refresh_prices(is_open=True),
    "price": lambda: collector.refresh_prices(is_open=False),
    "close": collector.close,
}


def collector_handler(event, context):  # noqa: ARG001 - Lambda signature
    mode = (event or {}).get("mode", "select")
    fn = _MODES.get(mode)
    if fn is None:
        log.warning("Unknown collector mode: %s", mode)
        return {"error": f"unknown mode {mode}"}
    processed = fn()
    log.info("Collector mode=%s processed %d", mode, processed)
    return {"mode": mode, "processed": processed}
