import unittest
from unittest.mock import Mock
from engine.coinbase_preview import CoinbasePreview


class CoinbasePreviewTests(unittest.TestCase):
    def setUp(self):
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
                    "available_balance": {"currency": "USD", "value": "25"},
                },
                {
                    "currency": "BTC",
                    "available_balance": {"currency": "BTC", "value": ".01"},
                },
            ],
            "has_next": False,
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
            "base_increment": ".00001",
            "base_min_size": ".00001",
            "base_max_size": "100",
        }
        self.client.preview_market_order_buy.return_value = {
            "quote_size": "4.90",
            "order_total": "4.93",
            "preview_id": "mock-buy",
            "commission_total": ".03",
            "errs": [],
        }
        self.client.preview_market_order_sell.return_value = {
            "base_size": ".001",
            "order_total": ".10",
            "preview_id": "mock-sell",
            "commission_total": ".03",
            "errs": [],
        }
        self.adapter = CoinbasePreview(self.client)

    def test_buy_reserves_fees_without_submitting(self):
        p = self.adapter.preview("BTC-USD", "buy", "5")
        self.assertEqual(p["requested"]["quote_size"], "4.90")
        self.assertFalse(p["live_enabled"])
        self.client.market_order_buy.assert_not_called()
        self.client.create_order.assert_not_called()

    def test_sell_preview_does_not_submit(self):
        p = self.adapter.preview("BTC-USD", "sell", ".001")
        self.assertEqual(p["preview_id"], "mock-sell")
        self.client.market_order_sell.assert_not_called()

    def test_missing_permission_rejected(self):
        self.client.get_api_key_permissions.return_value = {
            "portfolio_uuid": "test-portfolio",
            "can_view": True,
            "can_trade": False,
            "can_transfer": False,
        }
        with self.assertRaises(ValueError):
            self.adapter.preview("BTC-USD", "buy", "5")
        self.client.preview_market_order_buy.assert_not_called()

    def test_minimum_size_and_insufficient_funds(self):
        with self.assertRaises(ValueError):
            self.adapter.preview("BTC-USD", "buy", ".1")
        with self.assertRaises(ValueError):
            self.adapter.preview("BTC-USD", "sell", "1")

    def test_disabled_or_unknown_product_rejected(self):
        for field in (
            "is_disabled",
            "trading_disabled",
            "cancel_only",
            "limit_only",
            "post_only",
        ):
            self.client.get_product.return_value[field] = True
            with self.assertRaises(ValueError):
                self.adapter.preview("BTC-USD", "buy", "5")
            self.client.get_product.return_value[field] = False
        del self.client.get_product.return_value["trading_disabled"]
        with self.assertRaises(ValueError):
            self.adapter.preview("BTC-USD", "buy", "5")

    def test_excessive_fee_and_broker_error_rejected(self):
        self.client.preview_market_order_buy.return_value["commission_total"] = "1"
        with self.assertRaises(ValueError):
            self.adapter.preview("BTC-USD", "buy", "5")
        self.client.preview_market_order_buy.return_value.update(
            commission_total=".03", errs=["UNKNOWN"]
        )
        with self.assertRaises(ValueError):
            self.adapter.preview("BTC-USD", "buy", "5")

    def test_nonfinite_amount_and_oversized_budget_rejected(self):
        for size in ("NaN", "Infinity", "-1", "0", "5.01"):
            with self.assertRaises(ValueError):
                self.adapter.preview("BTC-USD", "buy", size)

    def test_no_submission_interface_is_exposed(self):
        self.assertFalse(hasattr(self.adapter, "submit"))
        self.assertFalse(hasattr(self.adapter, "create_order"))
