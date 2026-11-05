# Windows verification

Successful run: https://github.com/lakecityboi386-rgb/IronTradeAI/actions/runs/42110068448

Application source: `dc4c10ba5eeadcf4851828d0e8a04b1a68e7fb75` on `codex/windows-verification`.

The Windows job passed its Python suite (including native DPAPI round-trip and tamper rejection), frontend production build, Python sidecar bundling, Rust/Tauri compilation and NSIS packaging. It then installed the package, opened the normal release app, verified the office rendered, navigated the eight agents and account-link screen, and checked that closing the app stopped the engine. The test used native Windows accessibility and screen capture, not a special debug build.

Artifacts in the successful run:

| Artifact | GitHub artifact archive SHA-256 |
| --- | --- |
| NightShift-Windows-unsigned | `3e285ea12a7083a6bf188ecc14f33d8347243deb6c88a33818ff90144c3ecc6a` |
| NightShift-Windows-Smoke-Evidence | `c974bd98a8bc7193d2bff9b34dd9c4db62c4bcf542a431c2779eea09d3e63a94` |

These hashes identify GitHub's artifact archives, not individual installer files. Sign into GitHub, open the run, and download the installer artifact from **Artifacts**. Extract the ZIP and run the contained NSIS installer on Windows. The installer is unsigned.

No account credentials were imported and no real Coinbase orders were submitted. Broker execution, timeout, partial-fill and approval tests used mocked responses. Live submission remains disabled by default and requires a verified personal account, deliberate activation and a separate confirmation for every order. CI smoke success is not a claim of profitability or verified real-money execution.

The local Chromium suite also passed all seven browser checks. Documentation was updated after the successful native run; application code is unchanged from the verified revision above.
