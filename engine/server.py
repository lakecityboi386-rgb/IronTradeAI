"""Loopback-only service. No live submit endpoint. Start with python -m engine.server."""

import json
import os
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from .core import Engine
from .replay import compare
from .account_link import AccountLink
from .live_execution import LiveExecution
from .core import BOTS

ORIGINS = {
    "http://localhost:1420",
    "http://127.0.0.1:1420",
    "tauri://localhost",
    "http://tauri.localhost",
    "https://tauri.localhost",
}
TOKEN = secrets.token_urlsafe(32)
engine = Engine(
    Path(os.environ.get("IRONTRADE_DATA_DIR", str(Path.home() / ".irontrade")))
    / "paper.sqlite3"
)
account_link = AccountLink(
    Path(engine.db.execute("PRAGMA database_list").fetchone()[2]).parent
)
live = LiveExecution(
    Path(engine.db.execute("PRAGMA database_list").fetchone()[2]).parent
    / "live.sqlite3",
    account_link,
    lambda: engine.markets,
    lambda: engine.setting("kill") == "1",
)
auto = False


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # Never log request bodies or authentication headers.

    def respond(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        origin = self.headers.get("Origin")
        if origin in ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header(
            "Access-Control-Allow-Headers", "Content-Type, X-Nightshift-Token"
        )
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.respond({})

    def do_GET(self):
        if self.headers.get("Host", "").split(":")[0] not in ("localhost", "127.0.0.1"):
            return self.respond({"error": "Invalid host"}, 403)
        if self.path == "/api/state":
            return self.respond(
                {
                    **engine.snapshot(),
                    "token": TOKEN,
                    "auto": auto,
                    "coinbase_connection": account_link.status(),
                    "live": live.state(),
                }
            )
        self.respond({"error": "Not found"}, 404)

    def do_POST(self):
        global auto
        if (
            self.headers.get("Host", "").split(":")[0] not in ("localhost", "127.0.0.1")
            or self.headers.get("Origin") not in ORIGINS
            or not secrets.compare_digest(
                self.headers.get("X-Nightshift-Token", ""), TOKEN
            )
        ):
            return self.respond({"error": "Local session required"}, 403)
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 16384:
                raise ValueError("Invalid body length")
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError("Expected JSON object")
            if self.path == "/api/coinbase/connect":
                with live.lock:
                    live.deactivate()
                    result = account_link.connect(
                        data.get("api_key"),
                        data.get("api_secret"),
                        live.portfolio_fingerprint(),
                    )
            elif self.path == "/api/coinbase/disconnect":
                live.deactivate()
                result = account_link.disconnect()
            elif self.path == "/api/live/activate":
                result = live.activate(data.get("confirmation"))
            elif self.path == "/api/live/deactivate":
                result = live.deactivate()
            elif self.path == "/api/live/preview":
                requested_by = "Manual"
                product, side, amount = (
                    data.get("product"),
                    data.get("side"),
                    data.get("amount"),
                )
                if data.get("proposal_id"):
                    with engine.lock:
                        row = engine.db.execute(
                            "SELECT body,status FROM proposals WHERE id=?",
                            (data["proposal_id"],),
                        ).fetchone()
                        if not row or row["status"] != "pending":
                            raise ValueError("Pending bot proposal required")
                        proposal = json.loads(row["body"])
                        if (
                            proposal.get("origin") != "agent"
                            or proposal["side"] != "buy"
                            or time.time() - proposal["created"] > 90
                        ):
                            raise ValueError("Fresh bot entry proposal required")
                        product, side, amount, requested_by = (
                            proposal["product"],
                            "buy",
                            proposal["amount"],
                            proposal["bot"],
                        )
                result = live.preview(product, side, amount, requested_by)
            elif self.path == "/api/live/approve":
                result = live.approve(
                    data["id"], data["approval_token"], data["confirmation"]
                )
            elif self.path == "/api/live/cancel":
                result = live.cancel(data["id"], data["confirmation"])
            elif self.path == "/api/live/reconcile":
                result = live.reconcile(data["id"])
            elif self.path == "/api/propose":
                if data.get("mode", "paper") != "paper":
                    raise ValueError(
                        "Live orders are locked; this endpoint creates paper proposals only"
                    )
                result = engine.propose(
                    "Manual",
                    data["product"],
                    data["amount"],
                    data.get("side", "buy"),
                    data.get("position_id"),
                )
            elif self.path == "/api/decide":
                if not isinstance(data.get("approve"), bool):
                    raise ValueError("Explicit boolean decision required")
                result = engine.decide(data["id"], data["approve"])
            elif self.path == "/api/research":
                with engine.lock:
                    quote = engine.markets.get(data["product"])
                    if not quote:
                        raise ValueError("Verified historical candles unavailable")
                    result = compare(data["bot"], list(quote["candles"]))
            elif self.path == "/api/approval-policy":
                result = engine.set_approval_policy(data["policy"])
            elif self.path == "/api/kill":
                with live.lock:
                    result = engine.set_kill(data["enabled"])
            elif self.path == "/api/auto":
                if not isinstance(data.get("enabled"), bool):
                    raise ValueError("enabled must be boolean")
                auto = data["enabled"]
                result = {"auto": auto}
            elif self.path == "/api/live":
                return self.respond(
                    {
                        "error": "Live activation locked: broker integration and native security review incomplete. No real orders can be submitted."
                    },
                    403,
                )
            else:
                return self.respond({"error": "Unknown action"}, 404)
            self.respond(result)
        except (ValueError, KeyError, TypeError) as exc:
            self.respond({"error": str(exc)}, 400)
        except Exception:
            self.respond({"error": "Operation failed; no live order route exists"}, 500)


def worker():
    while True:
        try:
            engine.refresh()
            engine.protect()
            live.reconcile_active()
            if auto:
                engine.scan()
        except Exception:
            engine.market_error = (
                "Market worker unavailable; entries require fresh quotes"
            )
        time.sleep(30)


if __name__ == "__main__":
    threading.Thread(target=account_link.restore, daemon=True).start()
    threading.Thread(target=worker, daemon=True).start()
    print(
        "NightShift paper engine listening on 127.0.0.1:8765; live orders locked",
        flush=True,
    )
    ThreadingHTTPServer(("127.0.0.1", 8765), Handler).serve_forever()
