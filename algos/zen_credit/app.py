"""Render web service.

    GET  /health      -> 200, no auth. Liveness for Render's health probe / uptime checks.
    GET  /status      -> session, position state, last evaluation / signal (no secrets).
    POST /run-cycle   -> exactly one evaluation (cron-job.org). Requires CRON_TOKEN.
                         Returns a compact summary (< 2 KB): status, session, minute,
                         alpha, alpha2, signal, position, action, reason. Bulk data is
                         only ever logged server-side.
    POST /run         -> alias of /run-cycle.

Auth: ``X-Cron-Token: <token>`` header (preferred), ``?token=<token>`` query
parameter, or ``Authorization: Bearer <token>``; compared with
``hmac.compare_digest``. An unset CRON_TOKEN refuses every request (fails closed).

Concurrency: a cycle runs under an in-process lock and a fenced Firestore lease;
a second concurrent call returns 409 ``busy`` without touching state. Duplicate
calls for the same minute are additionally ignored by the minute ledger.
"""
from __future__ import annotations

import hmac
import logging
import os
import threading
from datetime import datetime

from flask import Flask, jsonify, request

from config import CONFIG
from main import HTTP_OK_STATUSES, Runner, setup_logging, summarize_cycle
from utils.time import IST

setup_logging(CONFIG)
log = logging.getLogger("zen_credit.web")

_runner: Runner | None = None
_runner_lock = threading.Lock()


def get_runner() -> Runner:
    global _runner
    with _runner_lock:
        if _runner is None:
            _runner = Runner.from_config(CONFIG)
        return _runner


def create_app(runner_factory=get_runner, cron_token: str | None = None) -> Flask:
    app = Flask(__name__)
    token = CONFIG.runtime.cron_token if cron_token is None else cron_token

    def token_ok() -> bool:
        if not token:
            log.error("CRON_TOKEN is not set; refusing every /run-cycle request")
            return False
        auth = request.headers.get("Authorization", "")
        supplied = (request.headers.get("X-Cron-Token") or request.args.get("token")
                    or (auth[7:] if auth.startswith("Bearer ") else "") or "")
        return hmac.compare_digest(str(supplied), str(token))

    @app.get("/health")
    def health():
        body = {"status": "ok", "service": "zen-credit", "strategy": CONFIG.runtime.strategy_name,
                "ts": datetime.now(IST).isoformat()}
        try:
            if _runner is not None or runner_factory is not get_runner:
                body.update(runner_factory().health())
        except Exception as exc:  # noqa: BLE001 - liveness must not fail on a DB hiccup
            body["detail"] = type(exc).__name__
        return jsonify(body), 200

    @app.get("/")
    def root():
        return jsonify({"service": "zen-credit",
                        "endpoints": ["GET /health", "GET /status", "POST /run-cycle"]}), 200

    @app.get("/status")
    def status():
        try:
            return jsonify(runner_factory().status()), 200
        except Exception as exc:  # noqa: BLE001
            log.exception("status failed")
            return jsonify({"status": "error", "error": type(exc).__name__}), 503

    def run_cycle():
        if not token_ok():
            log.warning("rejected run request: bad or missing token")
            return jsonify({"status": "unauthorized"}), 401
        try:
            runner = runner_factory()
        except Exception as exc:  # noqa: BLE001
            log.exception("runner failed to start")
            return jsonify({"status": "error", "stage": "startup", "error": type(exc).__name__}), 500
        result = runner.locked_cycle()
        busy = result.get("status") == "busy"
        summary = summarize_cycle(result, None if busy else runner.last_context)
        if busy:
            return jsonify(summary), 409
        return jsonify(summary), 200 if result.get("status") in HTTP_OK_STATUSES else 503

    @app.errorhandler(404)
    @app.errorhandler(405)
    @app.errorhandler(500)
    def compact_error(err):
        # Flask's default HTML error pages are replaced by tiny JSON bodies.
        code = getattr(err, "code", 500) or 500
        return jsonify({"status": "error", "code": code, "error": getattr(err, "name", "Internal Server Error")}), code

    app.add_url_rule("/run-cycle", "run_cycle", run_cycle, methods=["POST"])
    app.add_url_rule("/run", "run", run_cycle, methods=["POST"])
    return app


app = create_app()


if __name__ == "__main__":
    # Local development only. Render runs this under gunicorn (see render.yaml).
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
