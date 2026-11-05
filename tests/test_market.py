import json
import tempfile
import time
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from engine.core import Engine
class Response:
    def __init__(self, value): self.value=value
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def read(self): return json.dumps(self.value).encode()
class MarketTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.e=Engine(self.tmp.name+'/paper.sqlite3')
    def tearDown(self): self.e.db.close(); self.tmp.cleanup()
    def response(self, req, timeout):
        now=time.time()
        if '/candles' in req.full_url:
            return Response([[int(now-i*300),99,101,100,100+i*.01,20] for i in range(40)])
        return Response({'bid':'100','ask':'100.1','price':'100.05','volume':'1000','time':datetime.now(timezone.utc).isoformat()})
    @patch('engine.core.urlopen')
    def test_verified_quote_and_chronological_candles(self, get):
        get.side_effect=self.response
        state=self.e.refresh()
        self.assertEqual(len(state['markets']),3)
        q=state['markets']['BTC-USD']
        self.assertLess(q['candles'][0]['time'],q['candles'][-1]['time'])
        self.assertEqual(get.call_count,6)
        self.assertEqual(state['market_error'],'')
    @patch('engine.core.urlopen', side_effect=OSError('network unavailable'))
    def test_failure_clears_previous_prices(self, get):
        self.e.markets={'BTC-USD': {'price':100}}
        self.e.refresh()
        self.assertEqual(self.e.markets,{})
        self.assertIn('market unavailable',self.e.market_error)
    @patch('engine.core.urlopen')
    def test_old_exchange_timestamps_rejected(self, get):
        get.return_value=Response({'bid':'100','ask':'100.1','price':'100','volume':'1','time':'2020-01-01T00:00:00Z'})
        self.e.refresh()
        self.assertFalse(self.e.markets)
