# IronTrade AI — NightShift

Runnable milestone build: a React / Three.js trading office, eight selectable animated seated traders, a Tauri v2 Windows shell, and a local Python / SQLite paper engine. **This is an initial implementation, not a production trading application. Live orders are locked and no submission route exists.**

## Run in development

Requirements: Node 22+, Python 3.12+. No paid AI service or API key is required.

```sh
npm ci
# Terminal 1 (from the repository root)
python -m engine.server
# Terminal 2
npm run dev
```

Open the Vite development application on port 1420. The engine binds only to 127.0.0.1:8765. In a restricted cloud environment use its supported network permissions for installation and server startup. `IRONTRADE_DATA_DIR` chooses the SQLite directory; default is `~/.irontrade`. Never share this directory between paper test runs and personal trading history. The browser connects through Vite's `/api` proxy; the installed desktop uses the loopback engine directly.

For a writable cloud data directory:

```sh
IRONTRADE_DATA_DIR=/workspace/IronTradeAI/.runtime python -m engine.server
```

The initial screen renders the office immediately. Orbit with drag, zoom with the mouse wheel, and click a person or desk to inspect an agent. All office assets are original procedural geometry. Monitor bars are illustrative office graphics, **not market charts**. Actual charts in Live Markets appear only after verified Coinbase candles arrive.

## Paper workflow

Starting cash is $25. Each entry spends at most $5 including an estimated 0.6% fee. There can be at most five open positions. Quotes must be under 90 seconds old and spread at most 0.5%. Trades use the quoted ask/bid plus 5 bps slippage per side. Fees are simulation assumptions, not the user's actual Coinbase fee tier.

Use Manual Trading to preview a paper buy, inspect checks, then confirm. Paper Trading lists owned positions and full-position sell previews. The emergency switch blocks new entries; it does not liquidate positions. Manual exits still need a fresh quote. Duplicate confirmations cannot fill twice, and a transaction/lock rechecks capital and risk at execution.

Start paper agents explicitly in Paper Trading. The worker refreshes quotes every 30 seconds. Four versioned strategies originate distinct signals: Market Scout uses six-bar return with trend confirmation; Technical Analyst uses EMA/MACD/RSI agreement; Momentum Maverick requires a 20-close breakout; Mean Reversion Quant requires oversold conditions and a recovery. Liquidity Analyst abstains until order-book depth evidence is available. Wallet Tracker abstains without a verified on-chain source. Risk Officer independently checks all entries; Execution Specialist has no live routing. These eight roles are not yet eight independent validated strategies. Agents do not claim calibrated confidence or profitability. Daily realized losses plus current unrealized losses of $0.50 block new entries. Existing positions require fresh marks before any new entry. Paper stops (2% below simulated entry) and targets (4% above) are monitored each market refresh; gaps, fees, stale data and spread constraints can prevent or delay fills. The kill switch allows these owned protective exits.

Paper decisions persist indicators, source market conditions, reasoning, strategy version, checks, fees, and fills in SQLite. Performance currently reports net realized P/L, win rate, average P/L, and profit factor. A chronological 70/30 training/holdout evaluation and training-only RSI signal attribution are available in the engine state. Equal timestamps are kept on one side of the boundary; no challenger or automatic strategy promotion is enabled. Wilson win-rate intervals are descriptive, not claims of profitability.

## Market data

Only public `api.exchange.coinbase.com` REST endpoints are used, for BTC-USD, ETH-USD and SOL-USD. This is Coinbase **Exchange public market data**, not authenticated Advanced Trade connectivity. Failed/stale feeds are labelled unavailable and cannot authorize entries. No fallback fabricated prices are used. Exchange quotes and completed/recent candles are timestamp-checked. Network policy must permit that hostname; a saved environment draft alone does not apply it.

## Tests

```sh
python -m unittest discover -s tests -v
npm run build
# With the engine and Vite already running; Linux system Chromium is the default:
npx playwright test
```

Set `CHROMIUM_PATH` for another installed Chromium executable. Browser tests render the office, visit agent and manual trading screens, verify live activation is locked, and test persistence of the kill switch. Screenshots go to `test-results/`. Engine tests use explicit fixture quotes; they never contact a broker or submit a real order.

## Windows packaging

`.github/workflows/windows.yml` installs Rust, builds a Python sidecar using PyInstaller, compiles Tauri, and uploads an unsigned NSIS installer. Run it on GitHub Actions after pushing the committed code, or trigger workflow_dispatch. This Linux workspace has no Rust/native Windows runtime; **the Windows installer has not been built or tested here**.

For a local Windows build, install the Tauri v2 Windows prerequisites (Rust MSVC, Microsoft C++ build tools, WebView2), Python 3.12, and Node. Then from PowerShell:

```powershell
npm ci
python -m pip install pyinstaller==6.16.0
python -m PyInstaller --onefile --name nightshift-engine --paths . --hidden-import engine.server --hidden-import engine.core engine/launcher.py
New-Item -ItemType Directory -Force src-tauri/binaries
Copy-Item dist/nightshift-engine.exe src-tauri/binaries/nightshift-engine-x86_64-pc-windows-msvc.exe
npm run tauri -- build --target x86_64-pc-windows-msvc
```

The release shell starts the bundled sidecar and stops that child process when the app exits. Development uses the separately started Python service. The current fixed engine port permits only one instance. Installer launch, bundled engine discovery, data persistence after upgrade, WebView rendering, and process cleanup require native Windows verification before distribution.

## Remaining milestones

- Production character assets, walking/sitting transitions, group discussion gestures, market reactions, a richer Manhattan skyline and executive-office navigation.
- Verified wallet evidence, depth/volume models, role-specific risk/execution research, true inter-agent debates and calibrated confidence. The four speculative strategies have unit tests but no demonstrated out-of-sample profitability.
- Higher-frequency protective exit monitoring and more complete intraday equity sampling; the current engine records fresh mark-to-market equity at market refresh and derives sampled maximum drawdown.
- Longer-history walk-forward evaluation, independently collected forward-paper evidence, and a reviewed promotion policy. The Leaderboard now offers fixed champion/challenger replay on a chronological 70/30 split, with next-observation fills and explicit costs; automatic promotion remains disabled.
- Coinbase Advanced Trade authentication with OS-protected credentials, balance/product/size checks, previews, per-order approval, idempotency, reconciliation, unknown status and partial-fill handling. No credentials are collected in this build.
- Ollama chat integration; current questions return the agent's actual indicator explanation, not generated AI conversation.
- Successful Windows CI build and native installer smoke tests. CI configuration is not evidence of a passing Windows build.

Never enable real capital on the strength of a small number of paper wins. Stop prices cannot guarantee maximum realized loss. Do not submit real orders during development or testing.

## Strategy research

The Bot Leaderboard includes a champion/challenger panel for the four speculative agents. The engine fetches up to 300 actual five-minute candles, sorts chronologically, reserves the final 30% as holdout, and replays each fixed parameter set independently. Signals use only observations available at that point; fills use the next observation. Historical spread/slippage are assumptions, not measured past order books. A short history can yield zero trades, which is insufficient evidence, not a passing strategy. Research never modifies execution parameters or disables risk gates. No promotion button or execution endpoint exists.
