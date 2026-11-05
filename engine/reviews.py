"""Advisory agent opinions; only independent risk checks authorize eligibility."""

from .strategies import assess

NAMES = (
    "Market Scout",
    "Technical Analyst",
    "Wallet Tracker",
    "Liquidity Analyst",
    "Risk Officer",
    "Execution Specialist",
    "Momentum Maverick",
    "Mean Reversion Quant",
)


def team_review(quote, checks, side, mode="paper"):
    reviews = []
    for name in NAMES:
        if name == "Risk Officer":
            failed = [c["name"] for c in checks if not c["passed"]]
            opinion = "block" if failed else "eligible"
            reason = (
                "Blocked: " + "; ".join(failed)
                if failed
                else "All independent risk checks passed. User confirmation is still required under approval mode."
            )
        elif name == "Execution Specialist":
            opinion = "review"
            reason = (
                "Coinbase preview, account balances and product limits were checked. This live order still needs individual human confirmation."
                if mode == "live"
                else "Paper execution uses quoted bid/ask, 0.6% fee and 5 bps slippage per side. Live orders use a separate approval workflow."
            )
        else:
            signal = assess(name, quote)
            opinion = (
                "supports entry"
                if signal["action"] == "buy" and side == "buy"
                else "abstain"
            )
            reason = signal["reason"]
            if side == "sell":
                reason = (
                    "Long-entry strategy does not independently recommend an exit. "
                    + reason
                )
        reviews.append(
            {
                "bot": name,
                "opinion": opinion,
                "reason": reason,
                "binding": name == "Risk Officer",
            }
        )
    return reviews
