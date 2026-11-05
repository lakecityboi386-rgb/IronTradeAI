"""Authenticated Coinbase inspection and non-executing previews only.

The injected client is the official RESTClient. This adapter intentionally exposes
no create-order method until execution and reconciliation are independently ready.
"""

from decimal import Decimal, ROUND_DOWN
import hashlib
from .core import PRODUCTS


class CoinbasePreview:
    def __init__(self, client):
        self.client = client

    @staticmethod
    def data(response):
        return response if isinstance(response, dict) else response.to_dict()

    @staticmethod
    def number(value):
        number = Decimal(str(value))
        if not number.is_finite() or number < 0:
            raise ValueError("Broker returned an invalid numeric value")
        return number

    def inspect(self):
        permissions = self.data(self.client.get_api_key_permissions())
        if permissions.get("can_transfer") is not False:
            raise ValueError(
                "A key with transfer permission is not accepted; use a restricted View/Trade key"
            )
        if permissions.get("can_view") is not True:
            raise ValueError("Coinbase key does not have account view permission")
        # Never expose account identifiers, credential names, or raw SDK errors to UI/logs.
        identity = permissions.get("portfolio_uuid")
        if not isinstance(identity, str) or not identity:
            raise ValueError("A verifiable Coinbase portfolio identity is required")
        self.portfolio_id = identity
        accounts = self.data(
            self.client.get_accounts(limit=250, retail_portfolio_id=identity)
        )
        if accounts.get("has_next"):
            raise ValueError("Account pagination requires explicit portfolio selection")
        balances = {}
        for account in accounts.get("accounts", []):
            currency = account.get("currency")
            available = account.get("available_balance", {})
            if (
                currency in ("USD", "BTC", "ETH", "SOL")
                and available.get("currency") == currency
            ):
                balances[currency] = str(
                    self.number(balances.get(currency, 0))
                    + self.number(available.get("value", 0))
                )
        return {
            "portfolio_fingerprint": hashlib.sha256(identity.encode()).hexdigest(),
            "balances": balances,
            "can_trade": permissions.get("can_trade") is True,
            "live_enabled": False,
            "status": "Account inspected; submission locked",
        }

    def preview(self, product, side, amount):
        if product not in PRODUCTS or side not in ("buy", "sell"):
            raise ValueError("Supported spot USD product and side required")
        size = self.number(amount)
        if size <= 0 or (side == "buy" and size > 5):
            raise ValueError("Buy budget must be positive and at most $5")
        account = self.inspect()
        if not account["can_trade"]:
            raise ValueError(
                "Coinbase key lacks trade permission; no order can be authorized"
            )
        metadata = self.data(
            self.client.get_product(product_id=product, get_tradability_status=True)
        )
        if (
            metadata.get("product_type") != "SPOT"
            or metadata.get("is_disabled") is not False
        ):
            raise ValueError("Product is not an enabled spot market")
        if any(
            metadata.get(key) is not False
            for key in ("trading_disabled", "cancel_only", "limit_only", "post_only")
        ):
            raise ValueError(
                "Market orders are unavailable or product status is unknown"
            )
        if side == "buy":
            if size > self.number(account["balances"].get("USD", 0)):
                raise ValueError("Insufficient available USD balance")
            increment = self.number(metadata["quote_increment"])
            if increment <= 0:
                raise ValueError("Invalid product quote increment")
            # Reserve 2% of budget for fees, then validate the actual broker estimate.
            quote_size = ((size / Decimal("1.02")) / increment).to_integral_value(
                rounding=ROUND_DOWN
            ) * increment
            if quote_size < self.number(
                metadata["quote_min_size"]
            ) or quote_size > self.number(metadata["quote_max_size"]):
                raise ValueError("Quote amount violates product size limits")
            response = self.data(
                self.client.preview_market_order_buy(
                    product_id=product,
                    quote_size=str(quote_size),
                    retail_portfolio_id=self.portfolio_id,
                )
            )
            fee = self.number(response["commission_total"])
            if self.number(response["quote_size"]) != quote_size:
                raise ValueError("Broker preview sizing does not match the request")
            total = self.number(response["order_total"])
            if total <= 0 or total > size:
                raise ValueError("Broker preview total exceeds budget")
            if quote_size + fee > size or quote_size + fee > 5:
                raise ValueError("Estimated order total exceeds the approved budget")
            requested = {"quote_size": str(quote_size), "maximum_budget": str(size)}
        else:
            base = product.split("-")[0]
            if size > self.number(account["balances"].get(base, 0)):
                raise ValueError("Insufficient available asset balance")
            increment = self.number(metadata["base_increment"])
            if increment <= 0 or size % increment:
                raise ValueError("Sell amount violates product increment")
            if size < self.number(metadata["base_min_size"]) or size > self.number(
                metadata["base_max_size"]
            ):
                raise ValueError("Sell amount violates product size limits")
            response = self.data(
                self.client.preview_market_order_sell(
                    product_id=product,
                    base_size=str(size),
                    retail_portfolio_id=self.portfolio_id,
                )
            )
            fee = self.number(response["commission_total"])
            if (
                self.number(response["base_size"]) != size
                or self.number(response["order_total"]) <= 0
            ):
                raise ValueError("Broker sell preview sizing or proceeds are invalid")
            requested = {"base_size": str(size)}
        if (
            response.get("warning")
            or response.get("errs")
            or response.get("errors")
            or not response.get("preview_id")
        ):
            raise ValueError("Coinbase preview rejected or missing its identifier")
        return {
            "mode": "live_preview_only",
            "product": product,
            "side": side,
            "requested": requested,
            "estimated_fee": str(fee),
            "preview_id": response["preview_id"],
            "live_enabled": False,
            "status": "Non-executing broker preview. Account balances are not NightShift allocation. No order submitted.",
        }
