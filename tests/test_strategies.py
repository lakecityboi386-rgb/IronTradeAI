import unittest
from unittest.mock import patch
from engine.strategies import assess
from engine.replay import compare, replay


class StrategyTests(unittest.TestCase):
    def quote(self, closes, rsi=55):
        return {
            "candles": [{"time": i * 300, "close": c} for i, c in enumerate(closes)],
            "indicators": {"ema12": 102, "ema26": 100, "macd": 2, "rsi": rsi},
            "bid": 100,
            "ask": 100.1,
        }

    def test_missing_evidence_roles_abstain(self):
        q = self.quote([100] * 40)
        for bot in (
            "Wallet Tracker",
            "Liquidity Analyst",
            "Risk Officer",
            "Execution Specialist",
        ):
            self.assertEqual(assess(bot, q)["action"], "hold")

    def test_distinct_momentum_and_technical_signals(self):
        q = self.quote([100] * 39 + [100.1])
        self.assertEqual(assess("Technical Analyst", q)["action"], "buy")
        self.assertEqual(assess("Momentum Maverick", q)["action"], "hold")

    def test_reversion_requires_recovery(self):
        falling = self.quote([110] * 38 + [95, 94], rsi=20)
        recovering = self.quote([110] * 38 + [94, 95], rsi=20)
        self.assertEqual(assess("Mean Reversion Quant", falling)["action"], "hold")
        self.assertEqual(assess("Mean Reversion Quant", recovering)["action"], "buy")

    def test_challenger_is_stricter_and_uncalibrated(self):
        q = self.quote([100] * 39 + [100.3])
        self.assertEqual(assess("Market Scout", q)["action"], "buy")
        self.assertEqual(assess("Market Scout", q, True)["action"], "hold")
        self.assertIsNone(assess("Market Scout", q)["confidence"])

    def test_replay_rejects_duplicate_timestamps(self):
        with self.assertRaises(ValueError):
            replay("Market Scout", [{"time": 1, "close": 100}] * 40)

    def test_replay_comparison_keeps_holdout_separate(self):
        candles = [{"time": i, "close": 100 + i * 0.4} for i in range(300)]
        r = compare("Market Scout", candles)
        self.assertEqual(r["training_candles"], 210)
        self.assertEqual(r["holdout_candles"], 90)
        self.assertFalse(r["promotion_allowed"])
        self.assertEqual(set(r["results"]), {"champion", "challenger"})

    @patch("engine.replay.assess", return_value={"action": "buy"})
    def test_future_prices_do_not_change_earlier_fills(self, signal):
        first = [{"time": i, "close": 100 + i * 0.4} for i in range(200)]
        original = replay("Market Scout", first)
        modified = replay(
            "Market Scout",
            first + [{"time": 200 + i, "close": 200 - i * 0.2} for i in range(100)],
        )
        self.assertGreater(len(original), 1)
        self.assertEqual(
            [t for t in original if t["time"] < 199],
            [t for t in modified if t["time"] < 199],
        )

    @patch("engine.replay.assess", return_value={"action": "buy"})
    def test_entry_uses_next_observation_not_signal_close(self, signal):
        candles = [{"time": i, "close": 100} for i in range(30)] + [
            {"time": 30, "close": 200}
        ]
        trades = replay("Market Scout", candles)
        self.assertEqual(len(trades), 1)
        self.assertLess(trades[0]["pnl"], 0)
        self.assertGreater(trades[0]["pnl"], -0.1)
