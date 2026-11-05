import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from engine.core import Engine, indicators

class PaperEngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = self.tmp.name + '/paper.sqlite3'
        self.e = Engine(self.path)
        self.e.markets = {'BTC-USD': {'bid': 100.0, 'ask': 100.1, 'price':100.05, 'time':time.time(),
            'candles': [], 'indicators': {'ema12':101,'ema26':100,'macd':1,'rsi':55}}}
    def tearDown(self):
        self.e.db.close()
        self.tmp.cleanup()
    def buy(self, amount='5'):
        p = self.e.propose('Manual','BTC-USD',amount)
        self.assertEqual(p['status'], 'pending')
        return p
    def test_fee_spread_slippage_and_realized_roundtrip(self):
        p = self.buy()
        s = self.e.decide(p['id'], True)
        self.assertEqual(s['cash'],'20')
        self.assertEqual(len(s['positions']),1)
        pos = s['positions'][0]
        self.assertGreater(float(pos['entry']), 100.1)
        sell = self.e.propose('Manual','BTC-USD',pos['qty'],'sell',pos['id'])
        s = self.e.decide(sell['id'], True)
        self.assertEqual(len(s['positions']),0)
        self.assertLess(float(s['cash']),25)
        self.assertEqual(s['performance']['closed'],1)
        self.assertEqual(len(s['journal']),2)
    def test_duplicate_execution_is_rejected(self):
        p = self.buy()
        self.e.decide(p['id'],True)
        with self.assertRaises(ValueError): self.e.decide(p['id'],True)
        self.assertEqual(len(self.e.snapshot()['journal']),1)
    def test_concurrent_previews_cannot_overspend(self):
        ps = [self.buy() for _ in range(8)]
        def execute(p):
            try: self.e.decide(p['id'], True)
            except ValueError: pass
        with ThreadPoolExecutor(max_workers=8) as pool: list(pool.map(execute, ps))
        s = self.e.snapshot()
        self.assertEqual(len(s['positions']),5)
        self.assertEqual(float(s['cash']),0)
    def test_kill_rechecks_pending_preview_but_allows_exit(self):
        first = self.buy(); self.e.decide(first['id'],True)
        pending = self.buy(); self.e.set_kill(True)
        with self.assertRaises(ValueError): self.e.decide(pending['id'],True)
        pos = self.e.snapshot()['positions'][0]
        sell = self.e.propose('Manual','BTC-USD',pos['qty'],'sell',pos['id'])
        self.e.decide(sell['id'],True)
        self.assertEqual(len(self.e.snapshot()['positions']),0)
    def test_stale_and_missing_data_block(self):
        self.e.markets['BTC-USD']['time'] -= 100
        self.assertEqual(self.e.propose('Manual','BTC-USD','5')['status'],'blocked')
        self.e.markets = {}
        self.assertEqual(self.e.propose('Manual','BTC-USD','5')['status'],'blocked')
    def test_invalid_amounts_and_unknown_side(self):
        for amount in ('NaN','Infinity','-1','0','oops'):
            with self.assertRaises(ValueError): self.e.propose('Manual','BTC-USD',amount)
        with self.assertRaises(ValueError): self.e.propose('Manual','BTC-USD','5','short')
        self.assertEqual(self.e.propose('Manual','BTC-USD','5.01')['status'],'blocked')
    def test_wide_spread_and_unsupported_product(self):
        self.e.markets['BTC-USD']['ask']=102
        self.assertEqual(self.e.propose('Manual','BTC-USD','5')['status'],'blocked')
        self.assertEqual(self.e.propose('Manual','DOGE-USD','5')['status'],'blocked')
    def test_expired_preview_and_rejection(self):
        p = self.buy()
        import json
        p['created'] -= 100
        self.e.db.execute('UPDATE proposals SET body=? WHERE id=?',(json.dumps(p),p['id']))
        self.e.db.commit()
        with self.assertRaises(ValueError): self.e.decide(p['id'],True)
        self.e.decide(p['id'],False)
        self.assertEqual(self.e.snapshot()['proposals'][0]['status'],'rejected')
    def test_persistence(self):
        p=self.buy(); self.e.decide(p['id'],True)
        other=Engine(self.path)
        self.assertEqual(other.snapshot()['cash'],'20')
        self.assertEqual(len(other.snapshot()['positions']),1)
        other.db.close()
    def test_daily_loss_cutoff(self):
        p=self.buy(); self.e.decide(p['id'],True)
        pos=self.e.snapshot()['positions'][0]
        self.e.markets['BTC-USD'].update(bid=80,ask=80.1,price=80.05)
        sell=self.e.propose('Manual','BTC-USD',pos['qty'],'sell',pos['id'])
        self.e.decide(sell['id'],True)
        self.assertEqual(self.e.propose('Manual','BTC-USD','5')['status'],'blocked')
    def test_no_wallet_evidence_no_wallet_trades(self):
        self.e.scan()
        self.assertFalse(any(p['bot']=='Wallet Tracker' for p in self.e.snapshot()['proposals']))
    def test_indicator_flat_prices(self):
        self.assertEqual(indicators([100]*40)['rsi'],50)
        self.assertEqual(indicators([100]*40)['macd'],0)

if __name__ == '__main__': unittest.main()

class ProtectiveExitTests(unittest.TestCase):
    setUp = PaperEngineTests.setUp
    tearDown = PaperEngineTests.tearDown
    buy = PaperEngineTests.buy
    def test_stop_exit_still_operates_under_kill(self):
        p=self.buy();self.e.decide(p['id'],True)
        self.e.set_kill(True)
        self.e.markets['BTC-USD'].update(bid=95,ask=95.1)
        self.e.protect()
        s=self.e.snapshot()
        self.assertFalse(s['positions'])
        self.assertTrue(s['kill'])
        self.assertGreater(float(s['performance']['max_drawdown']),0)
    def test_unrealized_loss_blocks_entries(self):
        p=self.buy();self.e.decide(p['id'],True)
        self.e.markets['BTC-USD'].update(bid=80,ask=80.1)
        self.assertEqual(self.e.propose('Manual','BTC-USD','5')['status'],'blocked')
