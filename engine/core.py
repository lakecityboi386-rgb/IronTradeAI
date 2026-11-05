"""NightShift paper engine. Decimal accounting; persisted decisions; no live order route."""
import json
import math
import sqlite3
import time
import uuid
from decimal import Decimal
from pathlib import Path
from threading import RLock
from urllib.request import Request, urlopen
from .evaluation import evaluate

BOTS = [
    ('Market Scout', 'Cross-market trend discovery'),
    ('Technical Analyst', 'EMA / RSI / MACD confirmation'),
    ('Wallet Tracker', 'Verified on-chain evidence required'),
    ('Liquidity Analyst', 'Spread and depth quality'),
    ('Risk Officer', 'Independent risk review; abstains from originating orders'),
    ('Execution Specialist', 'Execution quality and reconciliation'),
    ('Momentum Maverick', 'Trend continuation and breakout'),
    ('Mean Reversion Quant', 'Oversold recovery'),
]
PRODUCTS = ('BTC-USD', 'ETH-USD', 'SOL-USD')
D = lambda value: Decimal(str(value))

def indicators(closes):
    def ema(period):
        value = closes[0]
        for close in closes[1:]:
            value += 2 / (period + 1) * (close - value)
        return value
    changes = [b - a for a, b in zip(closes[-15:-1], closes[-14:])]
    gain = sum(max(0, c) for c in changes) / len(changes)
    loss = sum(max(0, -c) for c in changes) / len(changes)
    return {'ema12': ema(12), 'ema26': ema(26), 'macd': ema(12) - ema(26),
            'rsi': 100 - 100 / (1 + gain / loss) if loss else (100 if gain else 50)}

class Engine:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = RLock()
        self.markets = {}
        self.market_error = 'Waiting for Coinbase public market data'
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
          INSERT OR IGNORE INTO settings VALUES ('cash', '25'), ('kill', '0');
          CREATE TABLE IF NOT EXISTS proposals (id TEXT PRIMARY KEY, body TEXT NOT NULL, status TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS positions (id TEXT PRIMARY KEY, bot TEXT, product TEXT, qty TEXT, cost TEXT, entry TEXT, opened REAL);
          CREATE TABLE IF NOT EXISTS journal (id TEXT PRIMARY KEY, body TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS equity (time REAL, value TEXT NOT NULL);
        ''')
        self.db.commit()

    def setting(self, key):
        return self.db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()[0]

    def set_kill(self, enabled):
        if not isinstance(enabled, bool):
            raise ValueError('enabled must be a boolean')
        with self.lock, self.db:
            self.db.execute("UPDATE settings SET value=? WHERE key='kill'", ('1' if enabled else '0',))
        return self.snapshot()

    def refresh(self):
        """Public Coinbase Exchange REST quotes/candles; no generated or fallback prices."""
        results = {}
        errors = []
        def get(path):
            req = Request('https://api.exchange.coinbase.com' + path, headers={'User-Agent': 'IronTrade-NightShift/0.1'})
            with urlopen(req, timeout=12) as response:
                return json.load(response)
        for product in PRODUCTS:
            try:
                ticker = get('/products/' + product + '/ticker')
                candles = get('/products/' + product + '/candles?granularity=300')
                candles = sorted(candles, key=lambda c: c[0])[-100:]
                bid, ask = float(ticker['bid']), float(ticker['ask'])
                if not (math.isfinite(bid) and math.isfinite(ask) and 0 < bid <= ask) or len(candles) < 30:
                    raise ValueError('Invalid quote or insufficient candles')
                price, volume = float(ticker['price']), float(ticker['volume'])
                if not math.isfinite(price) or price <= 0 or not math.isfinite(volume) or volume < 0:
                    raise ValueError('Invalid trade price or volume')
                observed = time.time()
                # Exchange ticker timestamp is mandatory; local receipt alone is not freshness.
                from datetime import datetime
                quoted_at = datetime.fromisoformat(ticker['time'].replace('Z', '+00:00')).timestamp()
                if abs(observed - quoted_at) > 90 or observed - candles[-1][0] > 900:
                    raise ValueError('Exchange data is stale')
                closes = [float(c[4]) for c in candles]
                if not all(math.isfinite(c) and c > 0 for c in closes):
                    raise ValueError('Invalid candle prices')
                results[product] = {'product': product, 'price': float(ticker['price']), 'bid': bid, 'ask': ask,
                    'volume': float(ticker['volume']), 'time': quoted_at,
                    'candles': [{'time': c[0], 'close': c[4]} for c in candles], 'indicators': indicators(closes),
                    'source': 'Coinbase Exchange public REST'}
            except Exception as exc:
                errors.append(product + ': ' + type(exc).__name__ + ' (market unavailable)')
        with self.lock:
            self.markets = results
            self.market_error = '; '.join(errors) if errors else ''
        return self.snapshot()

    def risk(self, product, amount, side='buy', position=None):
        checks = []
        def check(name, ok):
            checks.append({'name': name, 'passed': bool(ok)})
        q = self.markets.get(product)
        check('Supported spot USD product', product in PRODUCTS)
        check('Fresh verified market quote', q and 0 <= time.time() - q['time'] < 90)
        check('Positive finite amount', amount.is_finite() and amount > 0)
        if q:
            check('Spread below 0.5%', (q['ask'] - q['bid']) / q['ask'] <= .005)
        if side == 'buy':
            check('Emergency stop is off', self.setting('kill') == '0')
            check('Maximum entry $5 including fees', amount <= 5)
            check('Maximum five positions', self.db.execute('SELECT COUNT(*) FROM positions').fetchone()[0] < 5)
            check('Available paper balance', amount <= D(self.setting('cash')))
            rows = [json.loads(r[0]) for r in self.db.execute('SELECT body FROM journal')]
            today = time.strftime('%Y-%m-%d', time.gmtime())
            daily = sum(D(r.get('pnl') or 0) for r in rows if r.get('day') == today)
            unrealized = D(0)
            marks_valid = True
            for pos in self.db.execute('SELECT * FROM positions'):
                mark = self.markets.get(pos['product'])
                if not mark or not 0 <= time.time() - mark['time'] < 90:
                    marks_valid = False
                    continue
                unrealized += D(mark['bid']) * D(pos['qty']) * D('.993503') - D(pos['cost'])
            check('All held assets have fresh marks', marks_valid)
            check('Daily realized + unrealized loss below $0.50', daily + min(unrealized, D(0)) > D('-.50'))
        else:
            check('Owned position exists', position is not None)
            if position:
                check('Sell the owned position in full', amount == D(position['qty']))
        return checks

    def propose(self, bot, product, amount, side='buy', position_id=None):
        if bot not in [b[0] for b in BOTS] + ['Manual']:
            raise ValueError('Unknown agent')
        if side not in ('buy', 'sell'):
            raise ValueError('Unsupported side')
        try:
            value = D(amount)
        except Exception:
            raise ValueError('Invalid amount') from None
        if not value.is_finite() or value <= 0:
            raise ValueError('Amount must be finite and positive')
        with self.lock, self.db:
            position = self.db.execute('SELECT * FROM positions WHERE id=? AND product=?', (position_id, product)).fetchone()
            if side == 'sell' and position:
                bot = position['bot']
            q = self.markets.get(product)
            checks = self.risk(product, value, side, position)
            proposal = {'id': str(uuid.uuid4()), 'bot': bot, 'product': product, 'side': side, 'amount': str(value),
                'position_id': position_id, 'created': time.time(), 'checks': checks, 'mode': 'paper',
                'strategy_version': 'baseline-1', 'indicators': q['indicators'] if q else {},
                'entry': q['ask' if side == 'buy' else 'bid'] if q else None,
                'stop': q['ask'] * .98 if q and side == 'buy' else None,
                'target': q['ask'] * 1.04 if q and side == 'buy' else None,
                'estimated_fee': str(value * D('.006')) if side == 'buy' else None,
                'confidence': None, 'reasoning': self.reason(bot, q),
                'risk_decision': 'pass' if all(c['passed'] for c in checks) else 'reject'}
            status = 'pending' if proposal['risk_decision'] == 'pass' else 'blocked'
            self.db.execute('INSERT INTO proposals VALUES (?,?,?)', (proposal['id'], json.dumps(proposal), status))
            return {**proposal, 'status': status}

    def reason(self, bot, quote):
        if not quote:
            return 'No fresh market evidence; abstain.'
        i = quote['indicators']
        return f"{bot}: RSI {i['rsi']:.1f}, EMA12 {i['ema12']:.2f}, EMA26 {i['ema26']:.2f}. Baseline signal; confidence uncalibrated. Fees may exceed expected edge."

    def decide(self, proposal_id, approve):
        with self.lock, self.db:
            row = self.db.execute('SELECT * FROM proposals WHERE id=?', (proposal_id,)).fetchone()
            if not row or row['status'] != 'pending':
                raise ValueError('Proposal absent or already handled')
            p = json.loads(row['body'])
            if not approve:
                self.db.execute("UPDATE proposals SET status='rejected' WHERE id=?", (proposal_id,))
                return self.snapshot()
            if time.time() - p['created'] > 90:
                raise ValueError('Preview expired; create a new proposal')
            position = self.db.execute('SELECT * FROM positions WHERE id=? AND product=?', (p['position_id'], p['product'])).fetchone()
            checks = self.risk(p['product'], D(p['amount']), p['side'], position)
            if not all(c['passed'] for c in checks):
                raise ValueError('Risk Officer blocked execution; refresh preview')
            q = self.markets[p['product']]
            cash = D(self.setting('cash'))
            if p['side'] == 'buy':
                total = D(p['amount'])
                fee = total * D('.006')
                price = D(q['ask']) * D('1.0005')
                qty = (total - fee) / price
                self.db.execute('INSERT INTO positions VALUES (?,?,?,?,?,?,?)', (p['id'], p['bot'], p['product'], str(qty), str(total), str(price), time.time()))
                cash -= total
                pnl = None
            else:
                qty = D(position['qty'])
                price = D(q['bid']) * D('.9995')
                fee = qty * price * D('.006')
                proceeds = qty * price - fee
                pnl = proceeds - D(position['cost'])
                cash += proceeds
                self.db.execute('DELETE FROM positions WHERE id=?', (position['id'],))
            entry_evidence = None
            if p['side'] == 'sell':
                original = self.db.execute('SELECT body FROM journal WHERE id=?', (position['id'],)).fetchone()
                entry_evidence = json.loads(original[0]) if original else None
            event = {**p, 'entry_evidence': entry_evidence, 'checks': checks, 'fill': str(price), 'qty': str(qty), 'fee': str(fee),
                'pnl': str(pnl) if pnl is not None else None, 'time': time.time(),
                'day': time.strftime('%Y-%m-%d', time.gmtime()), 'market_conditions': q,
                'simulation': 'Paper: 0.6% fee, quoted spread, 5 bps slippage per side'}
            self.db.execute('INSERT INTO journal VALUES (?,?)', (p['id'], json.dumps(event)))
            self.db.execute("UPDATE settings SET value=? WHERE key='cash'", (str(cash),))
            self.db.execute("UPDATE proposals SET status='filled' WHERE id=?", (p['id'],))
            return self.snapshot()

    def scan(self):
        """Conservative baseline agents; evidence-gated roles abstain rather than invent signals."""
        with self.lock:
            for bot, _ in BOTS:
                if bot in ('Wallet Tracker', 'Risk Officer', 'Execution Specialist'):
                    continue
                for product, q in list(self.markets.items()):
                    i = q['indicators']
                    signal = i['rsi'] < 30 if bot == 'Mean Reversion Quant' else i['ema12'] > i['ema26'] and 45 < i['rsi'] < 68
                    if not signal:
                        continue
                    pending = self.db.execute("SELECT body FROM proposals WHERE status='pending'").fetchall()
                    if any(json.loads(r[0])['bot'] == bot and json.loads(r[0])['product'] == product for r in pending):
                        continue
                    p = self.propose(bot, product, '5')
                    if p['status'] == 'pending':
                        self.decide(p['id'], True)
            return self.snapshot()

    def protect(self):
        """Paper-only protective exits; kill switch blocks entries, never an owned exit."""
        with self.lock:
            for position in list(self.db.execute('SELECT * FROM positions')):
                q = self.markets.get(position['product'])
                if not q or not 0 <= time.time() - q['time'] < 90:
                    continue
                entry = D(position['entry'])
                bid = D(q['bid'])
                if bid <= entry * D('.98') or bid >= entry * D('1.04'):
                    p = self.propose(position['bot'], position['product'], position['qty'], 'sell', position['id'])
                    if p['status'] == 'pending':
                        self.decide(p['id'], True)
            self.record_equity()

    def record_equity(self):
        with self.lock, self.db:
            value = D(self.setting('cash'))
            for position in self.db.execute('SELECT * FROM positions'):
                q = self.markets.get(position['product'])
                if not q or not 0 <= time.time()-q['time'] < 90:
                    return
                value += D(q['bid']) * D(position['qty']) * D('.993503')
            self.db.execute('INSERT INTO equity VALUES (?,?)', (time.time(), str(value)))

    def snapshot(self):
        with self.lock:
            positions = [dict(r) for r in self.db.execute('SELECT * FROM positions')]
            journal = [json.loads(r[0]) for r in self.db.execute('SELECT body FROM journal ORDER BY rowid DESC')]
            proposals = [{**json.loads(r['body']), 'status': r['status']} for r in self.db.execute('SELECT * FROM proposals ORDER BY rowid DESC LIMIT 100')]
            for p in positions:
                q = self.markets.get(p['product'])
                p['unrealized'] = str(D(q['bid']) * D(p['qty']) * D('.994') - D(p['cost'])) if q and time.time()-q['time'] < 90 else None
            equity = [D(r[0]) for r in self.db.execute('SELECT value FROM equity ORDER BY time')]
            peak = D(25)
            drawdown = D(0)
            for value in equity:
                peak = max(peak, value)
                drawdown = max(drawdown, (peak-value)/peak if peak else D(0))
            closed = [D(r['pnl']) for r in journal if r.get('pnl') is not None]
            wins = [p for p in closed if p > 0]
            losses = [p for p in closed if p < 0]
            return {'mode': 'paper', 'cash': self.setting('cash'), 'kill': self.setting('kill') == '1',
                'live_enabled': False, 'markets': self.markets, 'market_error': self.market_error,
                'positions': positions, 'proposals': proposals, 'journal': journal,
                'bots': [{'name': name, 'strategy': strategy, 'state': 'reviewing' if self.markets else 'waiting for data',
                    'reasoning': 'Verified wallet feed not configured; abstaining.' if name == 'Wallet Tracker' else self.reason(name, next(iter(self.markets.values()), None))} for name, strategy in BOTS],
                'evaluation': evaluate(journal),
                'performance': {'max_drawdown': str(drawdown) if equity else None, 'equity_samples': len(equity), 'closed': len(closed), 'net': str(sum(closed)), 'win_rate': len(wins)/len(closed) if closed else None,
                    'average': str(sum(closed)/len(closed)) if closed else None,
                    'profit_factor': str(sum(wins)/abs(sum(losses))) if losses else None,
                    'learning': 'Insufficient time-ordered evidence. No strategy promotion enabled.'}}
