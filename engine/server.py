"""Loopback-only service. No live submit endpoint. Start with python -m engine.server."""
import json
import os
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from .core import Engine
from .replay import compare

ORIGINS = {'http://localhost:1420', 'http://127.0.0.1:1420', 'tauri://localhost', 'http://tauri.localhost', 'https://tauri.localhost'}
TOKEN = secrets.token_urlsafe(32)
engine = Engine(Path(os.environ.get('IRONTRADE_DATA_DIR', str(Path.home() / '.irontrade'))) / 'paper.sqlite3')
auto = False

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # Never log request bodies or authentication headers.

    def respond(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        origin = self.headers.get('Origin')
        if origin in ORIGINS:
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Vary', 'Origin')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-Nightshift-Token')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.respond({})

    def do_GET(self):
        if self.headers.get('Host', '').split(':')[0] not in ('localhost','127.0.0.1'):
            return self.respond({'error': 'Invalid host'}, 403)
        if self.path == '/api/state':
            return self.respond({**engine.snapshot(), 'token': TOKEN, 'auto': auto})
        self.respond({'error': 'Not found'}, 404)

    def do_POST(self):
        global auto
        if self.headers.get('Origin') not in ORIGINS or not secrets.compare_digest(self.headers.get('X-Nightshift-Token', ''), TOKEN):
            return self.respond({'error': 'Local session required'}, 403)
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 8192:
                raise ValueError('Invalid body length')
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError('Expected JSON object')
            if self.path == '/api/propose':
                result = engine.propose('Manual', data['product'], data['amount'], data.get('side', 'buy'), data.get('position_id'))
            elif self.path == '/api/decide':
                if not isinstance(data.get('approve'), bool):
                    raise ValueError('Explicit boolean decision required')
                result = engine.decide(data['id'], data['approve'])
            elif self.path == '/api/research':
                with engine.lock:
                    quote = engine.markets.get(data['product'])
                    if not quote:
                        raise ValueError('Verified historical candles unavailable')
                    result = compare(data['bot'], list(quote['candles']))
            elif self.path == '/api/kill':
                result = engine.set_kill(data['enabled'])
            elif self.path == '/api/auto':
                if not isinstance(data.get('enabled'), bool):
                    raise ValueError('enabled must be boolean')
                auto = data['enabled']
                result = {'auto': auto}
            elif self.path == '/api/live':
                return self.respond({'error': 'Live activation locked: broker integration and native security review incomplete. No real orders can be submitted.'}, 403)
            else:
                return self.respond({'error': 'Unknown action'}, 404)
            self.respond(result)
        except (ValueError, KeyError, TypeError) as exc:
            self.respond({'error': str(exc)}, 400)
        except Exception:
            self.respond({'error': 'Operation failed; no live order route exists'}, 500)

def worker():
    while True:
        try:
            engine.refresh()
            engine.protect()
            if auto:
                engine.scan()
        except Exception:
            engine.market_error = 'Market worker unavailable; entries require fresh quotes'
        time.sleep(30)

if __name__ == '__main__':
    threading.Thread(target=worker, daemon=True).start()
    print('NightShift paper engine listening on 127.0.0.1:8765; live orders locked', flush=True)
    ThreadingHTTPServer(('127.0.0.1', 8765), Handler).serve_forever()
