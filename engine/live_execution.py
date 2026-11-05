"""Persistent, human-approved spot execution. All tests inject mocked brokers.

No retry ever submits an order twice. Unknown submissions reserve capital until
reconciled. Activation is ephemeral, separate from stored credentials and paper.
"""

import hashlib
import json
import secrets
import sqlite3
import time
import uuid
from decimal import Decimal
from pathlib import Path
from threading import RLock
from .core import PRODUCTS
from .reviews import team_review

D = lambda x: Decimal(str(x))
ACTIVE = ("SUBMITTING", "UNKNOWN", "PENDING", "OPEN", "QUEUED", "CANCEL_QUEUED")
TERMINAL = ("FILLED", "CANCELLED", "EXPIRED", "FAILED", "REJECTED")


class LiveExecution:
    def __init__(self, path, account, quotes, entry_stopped):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = RLock()
        self.account = account
        self.quotes = quotes
        self.entry_stopped = entry_stopped
        self.enabled = False
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS identity (id INTEGER PRIMARY KEY CHECK(id=1), fingerprint TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS wallet (id INTEGER PRIMARY KEY CHECK(id=1), cash TEXT);
        INSERT OR IGNORE INTO wallet VALUES (1,'25');
        CREATE TABLE IF NOT EXISTS positions (product TEXT PRIMARY KEY, qty TEXT, cost TEXT);
        CREATE TABLE IF NOT EXISTS orders (id TEXT PRIMARY KEY, body TEXT, status TEXT, broker_id TEXT,
          applied_qty TEXT DEFAULT '0', applied_value TEXT DEFAULT '0', applied_fees TEXT DEFAULT '0');
        CREATE TABLE IF NOT EXISTS realized (id TEXT, time REAL, pnl TEXT);
        CREATE TABLE IF NOT EXISTS audit (time REAL, event TEXT, order_id TEXT);
        """)
        self.db.commit()

    def audit(self, event, order_id=""):
        self.db.execute(
            "INSERT INTO audit VALUES (?,?,?)", (time.time(), event, order_id)
        )

    def activate(self, confirmation):
        with self.lock:
            if confirmation != "ENABLE LIVE TRADING":
                raise ValueError("Explicit live activation confirmation required")
            status = self.account.status()
            if not status["connected"] or not status["secure_storage_available"]:
                raise ValueError(
                    "Verified account and secure Windows storage are required"
                )
            identity = self.account.adapter.inspect()
            if not identity["can_trade"]:
                raise ValueError(
                    "Coinbase trade permission is required for live activation"
                )
            if any(r["status"] in ("SUBMITTING", "UNKNOWN") for r in self.active()):
                raise ValueError("Reconcile unknown executions before activation")
            known = self.portfolio_fingerprint()
            if known and known != identity["portfolio_fingerprint"]:
                raise ValueError(
                    "This live ledger belongs to a different Coinbase portfolio"
                )
            with self.db:
                self.db.execute(
                    "INSERT OR IGNORE INTO identity VALUES (1,?)",
                    (identity["portfolio_fingerprint"],),
                )
            self.enabled = True
            with self.db:
                self.audit("live_activated")
        return self.state()

    def deactivate(self):
        with self.lock, self.db:
            self.enabled = False
            self.audit("live_deactivated")
        return self.state()

    def portfolio_fingerprint(self):
        row = self.db.execute("SELECT fingerprint FROM identity WHERE id=1").fetchone()
        return row[0] if row else None

    def adapter(self):
        if not self.enabled or self.account.adapter is None:
            raise ValueError("Live trading is disabled")
        identity = self.account.adapter.inspect()
        if identity["portfolio_fingerprint"] != self.portfolio_fingerprint():
            self.enabled = False
            raise ValueError("Linked portfolio changed; live trading disabled")
        return self.account.adapter

    def fresh_quote(self, product):
        q = self.quotes().get(product)
        if product not in PRODUCTS or not q or not 0 <= time.time() - q["time"] < 30:
            raise ValueError("Fresh supported market quote required")
        bid, ask = D(q["bid"]), D(q["ask"])
        if (
            not bid.is_finite()
            or not ask.is_finite()
            or not 0 < bid <= ask
            or (ask - bid) / ask > D(".005")
        ):
            raise ValueError("Invalid market or excessive spread")
        return q

    def active(self):
        return [
            r for r in self.db.execute("SELECT * FROM orders") if r["status"] in ACTIVE
        ]

    def guard(self, product, side, amount, exclude=None):
        if side not in ("buy", "sell"):
            raise ValueError("Spot buy or sell required")
        if not amount.is_finite() or amount <= 0:
            raise ValueError("Positive finite amount required")
        self.fresh_quote(product)
        active = [r for r in self.active() if r["id"] != exclude]
        if any(json.loads(r["body"])["product"] == product for r in active):
            raise ValueError("Another order for this product is unresolved")
        position = self.db.execute(
            "SELECT * FROM positions WHERE product=?", (product,)
        ).fetchone()
        if side == "sell":
            if not position or amount != D(position["qty"]):
                raise ValueError("Only a full owned NightShift position may be sold")
            return
        if self.entry_stopped():
            raise ValueError("Emergency stop blocks new live entries")
        if any(r["status"] in ("SUBMITTING", "UNKNOWN") for r in active):
            raise ValueError(
                "Unknown execution must be reconciled before another entry"
            )
        if amount > 5:
            raise ValueError("Maximum live entry including estimated fees is $5")
        if position:
            raise ValueError(
                "An existing position cannot be increased beyond its approved entry"
            )
        reserved = sum(
            (
                max(
                    D(0),
                    D(json.loads(r["body"])["amount"])
                    - D(r["applied_value"])
                    - D(r["applied_fees"]),
                )
                for r in active
                if json.loads(r["body"])["side"] == "buy"
            ),
            D(0),
        )
        cash = D(self.db.execute("SELECT cash FROM wallet WHERE id=1").fetchone()[0])
        cost = sum(
            (D(r["cost"]) for r in self.db.execute("SELECT cost FROM positions")), D(0)
        )
        if amount > cash - reserved or cost + reserved + amount > 25:
            raise ValueError("Live allocation or available cash limit exceeded")
        count = self.db.execute("SELECT COUNT(*) FROM positions").fetchone()[0] + sum(
            json.loads(r["body"])["side"] == "buy" for r in active
        )
        if count >= 5:
            raise ValueError("Maximum five live positions/reservations")
        day_start = int(time.time() // 86400) * 86400
        realized = sum(
            (
                min(D(r[0]), D(0))
                for r in self.db.execute(
                    "SELECT pnl FROM realized WHERE time>=?", (day_start,)
                )
            ),
            D(0),
        )
        unrealized = D(0)
        for p in self.db.execute("SELECT * FROM positions"):
            q = self.fresh_quote(p["product"])
            unrealized += D(q["bid"]) * D(p["qty"]) * D(".99") - D(p["cost"])
        if realized + min(unrealized, D(0)) <= D("-.50"):
            raise ValueError("2% live daily loss cutoff reached")

    def preview(self, product, side, amount, requested_by="Manual"):
        with self.lock:
            adapter = self.adapter()
            amount = D(amount)
            self.guard(product, side, amount)
            try:
                broker = adapter.preview(product, side, str(amount))
            except Exception:
                raise ValueError("Broker preview failed; no order submitted") from None
            checks = [
                {"name": name, "passed": True}
                for name in (
                    "Live activation",
                    "Fresh supported market quote",
                    "Acceptable quoted spread",
                    "Broker product and balance validation",
                    "Owned full position"
                    if side == "sell"
                    else "Allocation, position and daily loss limits",
                )
            ]
            reviews = team_review(self.fresh_quote(product), checks, side, mode="live")
            token = secrets.token_urlsafe(32)
            order = {
                "id": str(uuid.uuid4()),
                "product": product,
                "side": side,
                "amount": str(amount),
                "team_reviews": reviews,
                "requested_by": requested_by,
                "created": time.time(),
                "preview": broker,
                "approval_hash": hashlib.sha256(token.encode()).hexdigest(),
                "confirmation": f"{side.upper()} {product} {amount}",
                "client_order_id": str(uuid.uuid4()),
            }
            with self.db:
                self.db.execute(
                    "INSERT INTO orders(id,body,status) VALUES (?,?,?)",
                    (order["id"], json.dumps(order), "PREVIEW"),
                )
                self.audit("broker_preview_created", order["id"])
            public = {k: v for k, v in order.items() if k != "approval_hash"}
            return {
                **public,
                "approval_token": token,
                "mode": "live",
                "status": "PREVIEW",
            }

    def approve(self, order_id, approval_token, confirmation):
        with self.lock:
            adapter = self.adapter()
            row = self.db.execute(
                "SELECT * FROM orders WHERE id=?", (order_id,)
            ).fetchone()
            if not row or row["status"] != "PREVIEW":
                raise ValueError("Preview is absent or has already been consumed")
            p = json.loads(row["body"])
            if not isinstance(approval_token, str) or not isinstance(confirmation, str):
                raise ValueError("Exact individual human approval required")
            if (
                not secrets.compare_digest(
                    hashlib.sha256(approval_token.encode()).hexdigest(),
                    p["approval_hash"],
                )
                or confirmation != p["confirmation"]
            ):
                raise ValueError("Exact individual human approval required")
            if not 0 <= time.time() - p["created"] < 30:
                raise ValueError("Live preview expired; preview again")
            self.guard(p["product"], p["side"], D(p["amount"]))
            # Re-preview with fresh balances, product status and fees before consuming approval.
            current = adapter.preview(p["product"], p["side"], p["amount"])
            if (
                current["requested"] != p["preview"]["requested"]
                or current["estimated_fee"] != p["preview"]["estimated_fee"]
            ):
                raise ValueError(
                    "Order size or fees changed; a new human-approved preview is required"
                )
            if not 0 <= time.time() - p["created"] < 30:
                raise ValueError("Approval expired while refreshing the broker preview")
            self.guard(p["product"], p["side"], D(p["amount"]))
            p["preview"] = current
            p["human_approved_at"] = time.time()
            # Commit intent BEFORE network I/O. A crash/timeout must never enable a resubmit.
            with self.db:
                self.db.execute(
                    "UPDATE orders SET status='SUBMITTING', body=? WHERE id=?",
                    (json.dumps(p), order_id),
                )
                self.audit("human_approved_submission", order_id)
            config = {"market_market_ioc": current["requested"]}
            config["market_market_ioc"] = {
                k: v
                for k, v in config["market_market_ioc"].items()
                if k in ("quote_size", "base_size")
            }
            try:
                response = adapter.data(
                    adapter.client.create_order(
                        client_order_id=p["client_order_id"],
                        product_id=p["product"],
                        side=p["side"].upper(),
                        order_configuration=config,
                        preview_id=current["preview_id"],
                        retail_portfolio_id=adapter.portfolio_id,
                    )
                )
                success = response.get("success_response", {})
                broker_id = success.get("order_id")
                if response.get("success") is True and broker_id:
                    status = "PENDING"
                elif response.get("success") is False and response.get(
                    "error_response", {}
                ).get("error") in (
                    "INSUFFICIENT_FUND",
                    "INVALID_ARGUMENT",
                    "INVALID_PRICE",
                    "INVALID_SIZE",
                    "INVALID_PRODUCT_ID",
                    "INVALID_ORDER_TYPE",
                    "ORDER_PREVIEW_REQUIRED",
                    "PREVIEW_INVALID",
                ):
                    status = "REJECTED"
                    broker_id = None
                else:
                    status = "UNKNOWN"
                    broker_id = None
            except Exception:
                status = "UNKNOWN"
                broker_id = None
            with self.db:
                self.db.execute(
                    "UPDATE orders SET status=?, broker_id=? WHERE id=?",
                    (status, broker_id, order_id),
                )
                self.audit("submission_" + status.lower(), order_id)
            return self.state()

    def reconcile(self, order_id):
        with self.lock:
            # Reconciliation remains available after deactivation/kill switch.
            adapter = self.account.adapter
            if adapter is None:
                raise ValueError("Connect the account before reconciliation")
            if (
                adapter.inspect()["portfolio_fingerprint"]
                != self.portfolio_fingerprint()
            ):
                raise ValueError("Reconnect the original portfolio for reconciliation")
            row = self.db.execute(
                "SELECT * FROM orders WHERE id=?", (order_id,)
            ).fetchone()
            if not row or row["status"] == "PREVIEW":
                raise ValueError("No submitted order to reconcile")
            p = json.loads(row["body"])
            broker_id = row["broker_id"]
            try:
                if not broker_id:
                    cursor = None
                    for _ in range(10):
                        page = adapter.data(
                            adapter.client.list_orders(
                                limit=100,
                                cursor=cursor,
                                retail_portfolio_id=adapter.portfolio_id,
                            )
                        )
                        matches = [
                            o
                            for o in page.get("orders", [])
                            if o.get("client_order_id") == p["client_order_id"]
                        ]
                        if len(matches) > 1:
                            raise ValueError("Duplicate broker identity")
                        if matches:
                            broker_id = matches[0]["order_id"]
                            break
                        cursor = page.get("cursor")
                        if not page.get("has_next") or not cursor:
                            break
                    if not broker_id:
                        raise ValueError("Unresolved submission")
                order = adapter.data(adapter.client.get_order(order_id=broker_id))[
                    "order"
                ]
                if any(
                    order.get(k) != v
                    for k, v in [
                        ("client_order_id", p["client_order_id"]),
                        ("product_id", p["product"]),
                        ("side", p["side"].upper()),
                    ]
                ):
                    raise ValueError("Broker identity mismatch")
                status = order["status"]
                if status not in ACTIVE + TERMINAL:
                    raise ValueError("Unknown broker state")
                qty, value, fees = [
                    D(order[k]) for k in ("filled_size", "filled_value", "total_fees")
                ]
                oldq, oldv, oldf = [
                    D(row[k]) for k in ("applied_qty", "applied_value", "applied_fees")
                ]
                if (
                    any(not x.is_finite() or x < 0 for x in (qty, value, fees))
                    or qty < oldq
                    or value < oldv
                    or fees < oldf
                ):
                    raise ValueError("Invalid cumulative fill")
                dq, dv, df = qty - oldq, value - oldv, fees - oldf
                if status == "FILLED" and qty <= 0:
                    raise ValueError("Filled order has no verified fill")
                if (dv > 0 and dq <= 0) or (dq > 0 and dv <= 0):
                    raise ValueError("Incomplete fill accounting")
                position = self.db.execute(
                    "SELECT * FROM positions WHERE product=?", (p["product"],)
                ).fetchone()
                cash = D(
                    self.db.execute("SELECT cash FROM wallet WHERE id=1").fetchone()[0]
                )
                with self.db:
                    if p["side"] == "buy":
                        q = D(position["qty"]) if position else D(0)
                        cost = D(position["cost"]) if position else D(0)
                        if dq or df:
                            self.db.execute(
                                "INSERT OR REPLACE INTO positions VALUES (?,?,?)",
                                (p["product"], str(q + dq), str(cost + dv + df)),
                            )
                            cash -= dv + df
                    elif dq or df:
                        if not position and dq == 0 and dv == 0:
                            q, cost = D(0), D(0)
                        elif not position or dq > D(position["qty"]):
                            raise ValueError("Sell fill exceeds owned position")
                        else:
                            q, cost = D(position["qty"]), D(position["cost"])
                        basis = cost * dq / q if q else D(0)
                        pnl = dv - df - basis
                        self.db.execute(
                            "INSERT INTO realized VALUES (?,?,?)",
                            (order_id, time.time(), str(pnl)),
                        )
                        cash += dv - df
                        if q == dq:
                            self.db.execute(
                                "DELETE FROM positions WHERE product=?", (p["product"],)
                            )
                        else:
                            self.db.execute(
                                "UPDATE positions SET qty=?,cost=? WHERE product=?",
                                (str(q - dq), str(cost - basis), p["product"]),
                            )
                    self.db.execute("UPDATE wallet SET cash=? WHERE id=1", (str(cash),))
                    self.db.execute(
                        "UPDATE orders SET status=?,broker_id=?,applied_qty=?,applied_value=?,applied_fees=? WHERE id=?",
                        (status, broker_id, str(qty), str(value), str(fees), order_id),
                    )
                    self.audit("reconciled_" + status.lower(), order_id)
                    if cash < 0 or value + fees > D(p["amount"]) and p["side"] == "buy":
                        self.enabled = False
                        self.audit("unexpected_cost_live_disabled", order_id)
            except Exception:
                with self.db:
                    if row["status"] not in TERMINAL:
                        self.db.execute(
                            "UPDATE orders SET status='UNKNOWN' WHERE id=?", (order_id,)
                        )
                    self.audit("reconciliation_unresolved", order_id)
                raise ValueError(
                    "Order remains unresolved; no resubmission is permitted"
                ) from None
            return self.state()

    def cancel(self, order_id, confirmation):
        with self.lock:
            if confirmation != "CANCEL " + order_id:
                raise ValueError("Explicit cancellation confirmation required")
            adapter = self.account.adapter
            if adapter is None:
                raise ValueError("Connect the account before cancellation")
            if (
                adapter.inspect()["portfolio_fingerprint"]
                != self.portfolio_fingerprint()
            ):
                raise ValueError("Reconnect the original portfolio for cancellation")
            row = self.db.execute(
                "SELECT * FROM orders WHERE id=?", (order_id,)
            ).fetchone()
            if not row or row["status"] not in ACTIVE or not row["broker_id"]:
                raise ValueError(
                    "Reconcile the original broker order before requesting cancellation"
                )
            with self.db:
                self.db.execute(
                    "UPDATE orders SET status='CANCEL_QUEUED' WHERE id=?", (order_id,)
                )
                self.audit("human_requested_cancel", order_id)
            try:
                response = adapter.data(
                    adapter.client.cancel_orders(order_ids=[row["broker_id"]])
                )
                results = response.get("results", [])
                if not any(
                    r.get("order_id") == row["broker_id"] and r.get("success") is True
                    for r in results
                ):
                    raise ValueError("Cancellation not confirmed")
            except Exception:
                raise ValueError(
                    "Cancellation outcome requires reconciliation; reservation remains active"
                ) from None
            return self.state()

    def reconcile_active(self):
        if self.account.adapter is None:
            return
        with self.lock:
            ids = [r["id"] for r in self.active()]
        for order_id in ids:
            try:
                self.reconcile(order_id)
            except ValueError:
                pass

    def protection_alerts(self):
        alerts = []
        for p in self.db.execute("SELECT * FROM positions"):
            if D(p["qty"]) <= 0:
                continue
            try:
                q = self.fresh_quote(p["product"])
            except ValueError:
                alerts.append(
                    {
                        "product": p["product"],
                        "reason": "Market data unavailable; protective exit cannot be priced.",
                    }
                )
                continue
            reference = D(p["cost"]) / D(p["qty"])
            if D(q["bid"]) <= reference * D(".98") or D(q["bid"]) >= reference * D(
                "1.04"
            ):
                alerts.append(
                    {
                        "product": p["product"],
                        "reason": "Protective reference level reached. Preview and explicitly confirm an exit; no automatic live order was submitted.",
                    }
                )
        return alerts

    def state(self):
        with self.lock:
            orders = []
            for row in self.db.execute(
                "SELECT * FROM orders ORDER BY rowid DESC LIMIT 100"
            ):
                p = json.loads(row["body"])
                orders.append(
                    {
                        k: p[k]
                        for k in (
                            "id",
                            "product",
                            "side",
                            "amount",
                            "requested_by",
                            "created",
                        )
                    }
                    | {"status": row["status"], "filled_qty": row["applied_qty"]}
                )
            return {
                "enabled": self.enabled,
                "allocation": "25",
                "cash": self.db.execute(
                    "SELECT cash FROM wallet WHERE id=1"
                ).fetchone()[0],
                "positions": [
                    dict(r) for r in self.db.execute("SELECT * FROM positions")
                ],
                "orders": orders,
                "alerts": self.protection_alerts(),
                "unknown_execution": any(
                    r["status"] in ("SUBMITTING", "UNKNOWN") for r in self.active()
                ),
            }
