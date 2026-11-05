import tempfile
import time
import unittest
from unittest.mock import Mock
from engine.coinbase_preview import CoinbasePreview
from engine.live_execution import LiveExecution


class LiveExecutionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.client = Mock()
        self.client.get_api_key_permissions.return_value = {
            "portfolio_uuid": "test-portfolio",
            "can_view": True,
            "can_trade": True,
            "can_transfer": False,
        }
        self.client.get_accounts.return_value = {
            "accounts": [
                {
                    "currency": "USD",
                    "available_balance": {"currency": "USD", "value": "100"},
                },
                {
                    "currency": "BTC",
                    "available_balance": {"currency": "BTC", "value": "1"},
                },
            ]
        }
        self.client.get_product.return_value = {
            "product_type": "SPOT",
            "is_disabled": False,
            "trading_disabled": False,
            "cancel_only": False,
            "limit_only": False,
            "post_only": False,
            "quote_increment": ".01",
            "quote_min_size": "1",
            "quote_max_size": "1000",
            "base_increment": ".000001",
            "base_min_size": ".000001",
            "base_max_size": "100",
        }
        self.client.preview_market_order_buy.return_value = {
            "quote_size": "4.90",
            "order_total": "4.93",
            "preview_id": "mock-preview",
            "commission_total": ".03",
            "errs": [],
        }
        self.client.preview_market_order_sell.return_value = {
            "base_size": ".049",
            "order_total": "4.90",
            "preview_id": "mock-exit",
            "commission_total": ".03",
            "errs": [],
        }
        self.client.create_order.return_value = {
            "success": True,
            "success_response": {"order_id": "mock-order"},
        }
        self.account = Mock()
        self.account.adapter = CoinbasePreview(self.client)
        self.account.status.return_value = {
            "connected": True,
            "secure_storage_available": True,
        }
        self.stopped = False
        self.quotes = {"BTC-USD": {"time": time.time(), "bid": 100, "ask": 100.1}}
        self.live = LiveExecution(
            self.tmp.name + "/live.sqlite3",
            self.account,
            lambda: self.quotes,
            lambda: self.stopped,
        )

    def tearDown(self):
        self.live.db.close()
        self.tmp.cleanup()

    def preview(self):
        self.live.activate("ENABLE LIVE TRADING")
        return self.live.preview("BTC-USD", "buy", "5")

    def approve(self, p):
        return self.live.approve(p["id"], p["approval_token"], p["confirmation"])

    def fill(self, p, qty=".049", value="4.9", fees=".03", status="FILLED"):
        self.client.get_order.return_value = {
            "order": {
                "client_order_id": p["client_order_id"],
                "product_id": "BTC-USD",
                "side": "BUY",
                "filled_size": qty,
                "filled_value": value,
                "total_fees": fees,
                "status": status,
            }
        }
        return self.live.reconcile(p["id"])

    def test_disabled_by_default_and_explicit_activation(self):
        with self.assertRaises(ValueError):
            self.live.preview("BTC-USD", "buy", "5")
        with self.assertRaises(ValueError):
            self.live.activate("yes")
        self.client.create_order.assert_not_called()

    def test_individual_approval_and_duplicate_prevention(self):
        p = self.preview()
        with self.assertRaises(ValueError):
            self.live.approve(p["id"], "wrong", p["confirmation"])
        with self.assertRaises(ValueError):
            self.live.approve(p["id"], p["approval_token"], "yes")
        self.approve(p)
        with self.assertRaises(ValueError):
            self.approve(p)
        self.assertEqual(self.client.create_order.call_count, 1)

    def test_unknown_submission_is_not_retried_and_blocks_entries(self):
        p = self.preview()
        self.client.create_order.side_effect = TimeoutError("sensitive broker error")
        state = self.approve(p)
        self.assertTrue(state["unknown_execution"])
        with self.assertRaises(ValueError):
            self.approve(p)
        with self.assertRaises(ValueError):
            self.live.preview("BTC-USD", "buy", "5")
        self.assertEqual(self.client.create_order.call_count, 1)

    def test_reconciliation_applies_partial_fills_once(self):
        p = self.preview()
        self.approve(p)
        s = self.fill(p, qty=".02", value="2", fees=".01", status="OPEN")
        self.assertEqual(s["positions"][0]["qty"], "0.02")
        self.assertEqual(
            self.fill(p, qty=".02", value="2", fees=".01", status="OPEN")["cash"],
            s["cash"],
        )
        final = self.fill(p)
        self.assertEqual(final["cash"], "20.07")
        self.assertEqual(final["positions"][0]["qty"], "0.049")
        self.assertEqual(self.fill(p)["cash"], final["cash"])

    def test_kill_switch_rechecks_preview(self):
        p = self.preview()
        self.stopped = True
        with self.assertRaises(ValueError):
            self.approve(p)
        self.client.create_order.assert_not_called()

    def test_changed_fees_require_new_approval(self):
        p = self.preview()
        self.client.preview_market_order_buy.return_value["commission_total"] = ".04"
        with self.assertRaises(ValueError):
            self.approve(p)
        self.client.create_order.assert_not_called()

    def test_unknown_identity_never_applies_fills(self):
        p = self.preview()
        self.approve(p)
        self.client.get_order.return_value = {
            "order": {"client_order_id": "another-order"}
        }
        with self.assertRaises(ValueError):
            self.live.reconcile(p["id"])
        self.assertEqual(self.live.state()["cash"], "25")
        self.assertTrue(self.live.state()["unknown_execution"])

    def test_unknown_submission_discovered_by_client_id(self):
        p = self.preview()
        self.client.create_order.side_effect = TimeoutError()
        self.approve(p)
        self.client.list_orders.return_value = {
            "orders": [{"client_order_id": p["client_order_id"], "order_id": "found"}]
        }
        self.fill(p)
        self.assertFalse(self.live.state()["unknown_execution"])

    def test_restart_does_not_activate_or_forget_reservation(self):
        p = self.preview()
        self.approve(p)
        restarted = LiveExecution(
            self.tmp.name + "/live.sqlite3",
            self.account,
            lambda: self.quotes,
            lambda: False,
        )
        self.assertFalse(restarted.enabled)
        self.assertEqual(len(restarted.active()), 1)
        restarted.db.close()

    def test_cancel_requires_confirmation_and_preserves_reservation(self):
        p = self.preview()
        self.approve(p)
        with self.assertRaises(ValueError):
            self.live.cancel(p["id"], "yes")
        self.client.cancel_orders.return_value = {
            "results": [{"order_id": "mock-order", "success": True}]
        }
        state = self.live.cancel(p["id"], "CANCEL " + p["id"])
        self.assertEqual(state["orders"][0]["status"], "CANCEL_QUEUED")
        self.assertEqual(len(self.live.active()), 1)

    def test_live_owned_sell_reconciles_pnl_separately(self):
        p = self.preview()
        self.approve(p)
        self.fill(p)
        sell = self.live.preview("BTC-USD", "sell", ".049")
        self.approve(sell)
        self.client.get_order.return_value = {
            "order": {
                "client_order_id": sell["client_order_id"],
                "product_id": "BTC-USD",
                "side": "SELL",
                "filled_size": ".049",
                "filled_value": "4.90",
                "total_fees": ".03",
                "status": "FILLED",
            }
        }
        result = self.live.reconcile(sell["id"])
        self.assertEqual(result["positions"], [])
        self.assertEqual(result["cash"], "24.94")
        self.assertEqual(self.live.reconcile(sell["id"])["cash"], "24.94")

    def test_daily_loss_and_unowned_sells_are_blocked(self):
        self.preview()
        with self.assertRaises(ValueError):
            self.live.preview("BTC-USD", "sell", ".01")
        with self.live.db:
            self.live.db.execute(
                "INSERT INTO realized VALUES (?,?,?)", ("test", time.time(), "-.50")
            )
        with self.assertRaises(ValueError):
            self.live.preview("BTC-USD", "buy", "5")

    def test_stale_quote_and_preview_expiration(self):
        p = self.preview()
        self.quotes["BTC-USD"]["time"] -= 31
        with self.assertRaises(ValueError):
            self.approve(p)
        self.client.create_order.assert_not_called()

    def test_insufficient_live_allocation_and_wide_spread(self):
        self.preview()
        with self.live.db:
            self.live.db.execute("UPDATE wallet SET cash='4' WHERE id=1")
        with self.assertRaises(ValueError):
            self.live.preview("BTC-USD", "buy", "5")
        with self.live.db:
            self.live.db.execute("UPDATE wallet SET cash='25' WHERE id=1")
        self.quotes["BTC-USD"]["ask"] = 102
        with self.assertRaises(ValueError):
            self.live.preview("BTC-USD", "buy", "5")

    def test_ambiguous_rejection_stays_unknown(self):
        p = self.preview()
        self.client.create_order.return_value = {
            "success": False,
            "error_response": {"error": "DUPLICATE_ORDER"},
        }
        self.assertTrue(self.approve(p)["unknown_execution"])

    def test_explicit_rejection_releases_reservation(self):
        p = self.preview()
        self.client.create_order.return_value = {
            "success": False,
            "error_response": {"error": "INSUFFICIENT_FUND"},
        }
        self.assertEqual(self.approve(p)["orders"][0]["status"], "REJECTED")
        self.assertFalse(self.live.active())

    def test_protective_exit_requires_its_own_approval(self):
        p = self.preview()
        self.approve(p)
        self.fill(p)
        calls = self.client.create_order.call_count
        self.quotes["BTC-USD"].update(bid=90, ask=90.1)
        self.assertTrue(self.live.state()["alerts"])
        self.assertEqual(self.client.create_order.call_count, calls)
        self.stopped = True
        sell = self.live.preview("BTC-USD", "sell", ".049")
        self.assertEqual(sell["side"], "sell")
        self.assertEqual(self.client.create_order.call_count, calls)

    def test_portfolio_switch_cannot_reuse_approval_or_ledger(self):
        p = self.preview()
        self.client.get_api_key_permissions.return_value["portfolio_uuid"] = (
            "different-portfolio"
        )
        with self.assertRaises(ValueError):
            self.approve(p)
        self.assertFalse(self.live.enabled)
        self.client.create_order.assert_not_called()
        with self.assertRaises(ValueError):
            self.live.activate("ENABLE LIVE TRADING")

    def test_unknown_activation_and_reconciliation_after_deactivation(self):
        p = self.preview()
        self.client.create_order.side_effect = TimeoutError()
        self.approve(p)
        self.live.deactivate()
        with self.assertRaises(ValueError):
            self.live.activate("ENABLE LIVE TRADING")
        self.client.list_orders.return_value = {
            "orders": [
                {"client_order_id": p["client_order_id"], "order_id": "recovered"}
            ]
        }
        self.fill(p)
        self.assertFalse(self.live.enabled)
        self.assertFalse(self.live.state()["unknown_execution"])

    def test_gains_do_not_mask_daily_loss_cutoff(self):
        self.preview()
        with self.live.db:
            self.live.db.execute(
                "INSERT INTO realized VALUES (?,?,?)", ("gain", time.time(), "10")
            )
            self.live.db.execute(
                "INSERT INTO realized VALUES (?,?,?)", ("loss", time.time(), "-.50")
            )
        with self.assertRaises(ValueError):
            self.live.preview("BTC-USD", "buy", "5")
