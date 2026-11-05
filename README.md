# IronTrade AI — NightShift

React / Three.js office, eight selectable animated seated agents, a Tauri v2 Windows shell, and Python / SQLite trading services. Paper trading and human-approved Coinbase execution use separate ledgers. **The Windows installer, native user-bound encryption, installed UI and engine cleanup passed Windows CI. This remains a development build: authenticated Coinbase execution has only been tested with mocked broker responses. No real orders were submitted.**

## Run the development application

Requirements: Node 22+ and Python 3.12+.

```sh
npm ci
# Terminal 1, from the repository root:
python -m engine.server
# Terminal 2:
npm run dev
```

For writable cloud storage:

```sh
IRONTRADE_DATA_DIR=/workspace/IronTradeAI/.runtime python -m engine.server
```

Both services bind to loopback only: frontend 127.0.0.1:1420 and engine 127.0.0.1:8765. They are not public network listeners. Paper functionality needs no API key, paid AI service, or Python third-party package. `IRONTRADE_DATA_DIR` selects the data directory; otherwise it defaults to `~/.irontrade`. Use the environment's supported network permissions for installation and service startup.

Orbit the office by dragging, zoom with the wheel, and select a person or desk. All office assets are original procedural geometry. Office monitor bars are illustrative, not market charts. Live Markets charts use actual Coinbase candles only.

## Private Coinbase account linking

Open **Live Trading → Link your personal account** in the Windows desktop application.

1. Create a Coinbase CDP API key for Advanced Trade. Use the SDK-supported ECDSA format, View and Trade permissions, and **no Transfer permission**. The app rejects transfer-enabled keys.
2. Download the JSON key export. Keep it outside the repository and protect/remove the original export after importing it. The app cannot remove a file selected in a browser file picker.
3. Import the export with the app's file selector. The app verifies account access with read-only requests before saving anything.
4. Windows DPAPI encrypts the key for the signed-in Windows user. No plaintext credential file, browser storage, source-code insertion, or credential logging is used. The key exists in process memory when signing requests. Other programs running as your user can still pose a risk.
5. Linking does not activate trading. Type `ENABLE LIVE TRADING` in the activation field only when deliberately choosing live operation. Activation resets on engine restart.

**Do not paste keys into chat.** Import is disabled in Linux/cloud browsers because Windows user-bound secure storage is unavailable. No insecure storage fallback exists. Unlinking removes the encrypted key and disables live submission; it does not cancel orders already sent to Coinbase.

For Windows development, install the official SDK into the Python environment running the engine:

```powershell
python -m pip install -r requirements-coinbase.txt
```

The Windows packaging workflow installs and bundles the SDK. Account linking uses `api.coinbase.com`; public market data uses `api.exchange.coinbase.com`. Both hosts must be reachable. No real credentials are configured in the development environment.

## Trade alongside the agents

Manual and bot proposals share team review. Each paper proposal includes eight evidence-based reviews. Risk Officer checks are mandatory; the other opinions are advisory and may disagree. The default policy requires your confirmation before bot paper entries. Paper Trading has a separate explicit option for automatic risk-approved paper entries. Manual tickets always require confirmation.

Starting paper agents starts scanning, not live trading. Four versioned speculative strategies are implemented: Market Scout, Technical Analyst, Momentum Maverick and Mean Reversion Quant. Wallet Tracker abstains without verified on-chain evidence; Liquidity Analyst abstains without order-book depth. Risk and execution roles do not originate speculative signals. These rules have tests, not demonstrated profitability.

After deliberate live activation, the Live Trading panel can create a broker preview for a manual ticket or a pending bot entry proposal. Inspect it and type the exact order confirmation phrase. Each preview has a one-use approval token and expires after 30 seconds. **A bot cannot approve a live order on your behalf.**

## Execution safeguards

- Portfolio-bound, separate paper and live SQLite files; live capital is a tracked $25 allocation, not your full Coinbase balance.
- Spot USD markets only: BTC-USD, ETH-USD and SOL-USD. No leverage or futures.
- Maximum live entry budget $5 including estimated fees; maximum allocation $25; maximum five positions/reservations.
- Fresh quotes, maximum 0.5% spread, product tradability, minimum/maximum sizes and increments, available account balances, and mandatory preview validation.
- A conservative 2% daily realized-loss-plus-unrealized-loss entry cutoff and emergency entry stop. Realized gains do not offset realized losses in this gate. All held assets require fresh marks before another entry.
- Balances, product status, sizing and estimated fees are refreshed before submission. Changed sizing or fees require new approval. Preview buys reserve fee headroom. Actual broker fees/fills can differ; unexpected cost overruns disable submission for inspection.
- Durable intent and a unique client order ID are committed **before** network submission. Consumed approvals cannot submit twice.
- Timeouts and ambiguous responses remain `UNKNOWN`, retain allocation reservations and block entries. No blind submission retry exists. Reconciliation searches by the original client order ID if no broker order ID was received.
- Partial fills apply cumulative size, value and fees incrementally and idempotently. Partial fills remain owned positions when an order is cancelled.
- Explicit cancellation requests retain reservations until broker reconciliation. A cancellation request does not guarantee the order cannot fill.
- Reconciliation continues after deactivation and the entry kill switch. Disconnection prevents broker operations until the account is linked again.
- Protective live levels generate alerts, **not automatic orders**. Exits need their own preview and human confirmation. Paper protective exits can execute automatically. Stop/reference levels cannot guarantee a maximum loss.

The ledger stores a hashed portfolio binding and refuses cross-portfolio key changes or approval reuse. The execution journal exposes order state and reconciliation controls. It never exposes credentials. Broker exception text is not returned to the UI or logs.

## Paper and research

Paper starting cash is $25, with maximum $5 entries and five positions. Simulations use quoted bid/ask, 0.6% fees and 5 bps slippage per side. These are assumptions, not your broker fee tier. Paper stop/target monitoring runs at refresh time and can be delayed by stale data or market gaps. The entry kill switch does not liquidate positions.

Public quotes and up to 300 five-minute candles come from Coinbase Exchange REST. Failed or stale feeds are labelled unavailable; no fallback fabricated market prices authorize trades. Historical monitor graphics and test fixtures are not live data.

The Bot Leaderboard compares fixed champion/challenger rules using a chronological 70/30 split, next-observation fills, fees and slippage. Training and holdout remain separate. Short samples or zero trades are insufficient evidence. No automatic strategy promotion is implemented, and research cannot disable risk controls.

## Validation

```sh
python -m unittest discover -s tests -v
npm run build
# With engine and Vite already running; defaults to system Chromium on Linux:
npm run test:browser
```

Set `CHROMIUM_PATH` for another installed browser. All broker execution tests use mocks; browser live-order tests intercept account/order routes. They never send real orders. Two native DPAPI tests are skipped on Linux; both executed successfully in the Windows verification run. Screenshots are saved in ignored `test-results/`.

## Windows packaging

`.github/workflows/windows.yml` runs native Windows tests, installs the SDK, bundles the Python engine with PyInstaller, builds Tauri and uploads an unsigned NSIS installer. The [Windows verification run](https://github.com/lakecityboi386-rgb/IronTradeAI/actions/runs/42110068448) passed. It built and installed the NSIS package, verified the native release UI and rendered office, checked all eight agents and account-link controls, and confirmed engine cleanup. Download **NightShift-Windows-unsigned** from that run’s Artifacts section. See [VERIFICATION.md](VERIFICATION.md) for the exact tested source and archive digest. Verify your own read-only account connection before deliberately enabling real-money submission.

Windows prerequisites: Node, Python, Rust MSVC, Microsoft C++ build tools and WebView2. Local PowerShell packaging commands:

```powershell
npm ci
python -m pip install pyinstaller==6.16.0 -r requirements-coinbase.txt
python -m unittest discover -s tests -v
python -m PyInstaller --onefile --name nightshift-engine --paths . --hidden-import engine.server --hidden-import engine.core --hidden-import coinbase.rest engine/launcher.py
New-Item -ItemType Directory -Force src-tauri/binaries
Copy-Item dist/nightshift-engine.exe src-tauri/binaries/nightshift-engine-x86_64-pc-windows-msvc.exe
npm run tauri -- build --target x86_64-pc-windows-msvc
```

Release launches and stops its bundled engine child. Live activation does not survive restart. Verify engine discovery, DPAPI storage, import/unlink, installer upgrades, reconciliation and process cleanup on Windows. The fixed engine port currently supports one instance. Do not run the desktop with elevated administrator privileges.

## Remaining work

Production character assets, walking/discussion animation, richer office navigation, verified wallet/depth evidence, longer independent forward strategy validation, Ollama conversation, and real authenticated broker verification, code signing and longer native usage validation remain outstanding. Native Windows installation and UI smoke verification have passed. No real orders may be submitted during development or testing. Mocked safeguard tests do not establish production readiness or profitability.
