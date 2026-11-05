"""Time-ordered, fee-net paper evaluation. Never changes execution policy."""

from collections import defaultdict
from math import sqrt


def summarize(trades):
    pnl = [float(t["pnl"]) for t in trades if t.get("pnl") is not None]
    positive, negative = sum(max(p, 0) for p in pnl), -sum(min(p, 0) for p in pnl)
    n = len(pnl)
    wins = sum(p > 0 for p in pnl)
    # Wilson interval is descriptive, not a prediction or probability of profitability.
    if n:
        z = 1.96
        rate = wins / n
        denom = 1 + z * z / n
        center = (rate + z * z / (2 * n)) / denom
        radius = z * sqrt(rate * (1 - rate) / n + z * z / (4 * n * n)) / denom
        interval = [max(0, center - radius), min(1, center + radius)]
    else:
        interval = None
    return {
        "trades": n,
        "net": sum(pnl),
        "win_rate": wins / n if n else None,
        "mean": sum(pnl) / n if n else None,
        "profit_factor": positive / negative if negative else None,
        "win_rate_interval_95": interval,
    }


def evaluate(journal):
    ordered = sorted(
        (t for t in journal if t.get("pnl") is not None), key=lambda t: t["time"]
    )
    split = int(len(ordered) * 0.7)
    train, test = ordered[:split], ordered[split:]
    # Move equal timestamps out of training to prevent a boundary leaking into both sets.
    while train and test and train[-1]["time"] >= test[0]["time"]:
        test.insert(0, train.pop())
    signals = defaultdict(list)
    for trade in train:
        entry = trade.get("entry_evidence") or {}
        rsi = entry.get("indicators", {}).get("rsi")
        if rsi is not None:
            signals[
                "oversold" if rsi < 30 else "overbought" if rsi > 70 else "neutral"
            ].append(trade)
    return {
        "training": summarize(train),
        "holdout": summarize(test),
        "training_signal_attribution": {
            key: summarize(value) for key, value in signals.items()
        },
        "promotion_allowed": False,
        "status": "Observational baseline only; no independently replayed challenger.",
        "chronological_split": 0.7,
        "minimum_holdout_for_review": 30,
        "sufficient_holdout": len(test) >= 30,
    }
