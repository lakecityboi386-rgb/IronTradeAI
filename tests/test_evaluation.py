import unittest
from engine.evaluation import evaluate, summarize
class EvaluationTests(unittest.TestCase):
    def test_chronological_holdout_never_uses_training_outcomes(self):
        trades=[{'time':t,'pnl':1 if t<7 else -1,'entry_evidence':{'indicators':{'rsi':20}}} for t in range(10)]
        result=evaluate(list(reversed(trades)))
        self.assertEqual(result['training']['net'],7)
        self.assertEqual(result['holdout']['net'],-3)
        self.assertEqual(result['training_signal_attribution']['oversold']['trades'],7)
        self.assertFalse(result['promotion_allowed'])
        self.assertFalse(result['sufficient_holdout'])
    def test_equal_timestamp_does_not_leak(self):
        r=evaluate([{'time':1,'pnl':1}]*10)
        self.assertEqual(r['training']['trades'],0)
        self.assertEqual(r['holdout']['trades'],10)
    def test_no_evidence_does_not_invent_confidence(self):
        self.assertIsNone(summarize([])['win_rate_interval_95'])
