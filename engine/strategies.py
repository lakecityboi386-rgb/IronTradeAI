"""Deterministic, versioned paper signals. Missing evidence produces abstention."""
from math import isfinite

VERSION = 'signals-2'

def assess(bot, quote, challenger=False):
    abstain = lambda reason: {'action':'hold','reason':reason,'version':VERSION,'confidence':None}
    if not quote:
        return abstain('No verified market evidence.')
    if bot == 'Wallet Tracker':
        return abstain('No independently verified on-chain wallet source is configured.')
    if bot == 'Risk Officer':
        return abstain('Independent risk gate; never originates its own speculative entries.')
    if bot == 'Execution Specialist':
        return abstain('Execution-quality role; no independent speculative entry mandate.')
    candles = quote.get('candles', [])
    if len(candles) < 30:
        return abstain('At least 30 chronological candles are required.')
    closes = [float(c['close']) for c in candles]
    if not all(isfinite(c) and c > 0 for c in closes):
        return abstain('Invalid candle prices.')
    i = quote['indicators']
    rsi, fast, slow = i['rsi'], i['ema12'], i['ema26']
    spread = (quote['ask']-quote['bid'])/quote['ask']
    recent_return = closes[-1]/closes[-7]-1
    threshold = .004 if challenger else .002
    if bot == 'Market Scout':
        signal = recent_return > threshold and fast > slow and 40 < rsi < 65
        evidence = f'Six-bar return {recent_return:.2%}; trend confirmation {fast > slow}.'
    elif bot == 'Technical Analyst':
        signal = fast > slow and i['macd'] > 0 and 50 < rsi < (60 if challenger else 65)
        evidence = f'EMA12 {fast:.2f} vs EMA26 {slow:.2f}; MACD {i["macd"]:.4f}; RSI {rsi:.1f}.'
    elif bot == 'Liquidity Analyst':
        # No depth feed: spread alone cannot establish executable liquidity.
        return abstain(f'Quoted spread {spread:.3%}; order-book depth evidence unavailable, so no entry.')
    elif bot == 'Momentum Maverick':
        breakout = max(closes[-21:-1])
        signal = closes[-1] > breakout*(1+threshold) and 50 < rsi < 75
        evidence = f'Close {closes[-1]:.2f}; prior 20-close high {breakout:.2f}; RSI {rsi:.1f}.'
    elif bot == 'Mean Reversion Quant':
        mean = sum(closes[-20:])/20
        signal = rsi < (25 if challenger else 30) and closes[-1] < mean*.99 and closes[-1] > closes[-2]
        evidence = f'RSI {rsi:.1f}; 20-bar mean {mean:.2f}; recovery confirmation {closes[-1] > closes[-2]}.'
    else:
        return abstain('Manual ticket; no automated strategy applied.')
    return {'action':'buy' if signal else 'hold','reason':evidence,'version':VERSION+('-challenger' if challenger else '-champion'),'confidence':None}
