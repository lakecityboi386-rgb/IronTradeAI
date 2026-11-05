"""Matched, forward-only replay: signals at close, entry at next close.

Fees/spread/slippage are explicit assumptions. These are research results, not live
market prices or an authorization to change the execution risk policy.
"""

from math import isfinite
from .core import indicators
from .strategies import assess
from .evaluation import summarize

RESEARCH_BOTS = (
    "Market Scout",
    "Technical Analyst",
    "Momentum Maverick",
    "Mean Reversion Quant",
)


def replay(bot, candles, challenger=False):
    ordered = sorted(candles, key=lambda c: c["time"])
    if len({c["time"] for c in ordered}) != len(ordered):
        raise ValueError("Duplicate candle timestamps")
    position = None
    pending = False
    trades = []
    for index, candle in enumerate(ordered):
        price = float(candle["close"])
        if not isfinite(price) or price <= 0:
            raise ValueError("Invalid price")
        # Evaluate a previous close's signal on the next observation only.
        if pending and position is None:
            entry = price * 1.001
            position = {"qty": 4.97 / entry, "entry": entry, "time": candle["time"]}
        pending = False
        if position:
            if (
                price <= position["entry"] * 0.98
                or price >= position["entry"] * 1.04
                or index == len(ordered) - 1
            ):
                proceeds = position["qty"] * price * 0.999 * 0.994
                trades.append({"time": candle["time"], "pnl": proceeds - 5})
                position = None
            continue
        if index >= 29 and index < len(ordered) - 1:
            history = ordered[: index + 1]
            quote = {
                "candles": history,
                "indicators": indicators([float(c["close"]) for c in history]),
                "bid": price * 0.9995,
                "ask": price * 1.0005,
            }
            pending = assess(bot, quote, challenger)["action"] == "buy"
    return trades


def compare(bot, candles):
    if bot not in RESEARCH_BOTS:
        raise ValueError("Agent has no replayable speculative strategy")
    ordered = sorted(candles, key=lambda c: c["time"])
    boundary = int(len(ordered) * 0.7)
    train, holdout = ordered[:boundary], ordered[boundary:]
    if train and holdout and train[-1]["time"] >= holdout[0]["time"]:
        raise ValueError("Training and holdout timestamps overlap")
    results = {}
    for name, challenger in [("champion", False), ("challenger", True)]:
        results[name] = {
            "training": summarize(replay(bot, train, challenger)),
            "holdout": summarize(replay(bot, holdout, challenger)),
        }
    return {
        "bot": bot,
        "results": results,
        "training_candles": len(train),
        "holdout_candles": len(holdout),
        "promotion_allowed": False,
        "status": "Research comparison only. Independent forward paper evidence required.",
        "assumptions": "$5 isolated trades; 0.6% fees/side; 10 bps combined spread/slippage/side; next-observation fills; no leverage",
    }
