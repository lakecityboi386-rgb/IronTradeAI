import { useEffect, useState, Component, ReactNode } from "react";
import CoinbasePanel from "./CoinbasePanel";
import Office, { names, colors } from "./Office";
type Check = { name: string; passed: boolean };
type Proposal = {
  id: string;
  bot: string;
  strategy_version: string;
  product: string;
  side: string;
  amount: string;
  estimated_notional?: string | null;
  amount_unit?: string;
  entry: number | null;
  stop: number | null;
  target: number | null;
  estimated_fee: string | null;
  origin?: string;
  requested_by?: string;
  team_reviews?: {
    bot: string;
    opinion: string;
    reason: string;
    binding: boolean;
  }[];
  decision?: { actor: string; approved: boolean; time: number };
  checks: Check[];
  reasoning: string;
  status: string;
  created: number;
  indicators: Record<string, number>;
};
type Market = {
  price: number;
  bid: number;
  ask: number;
  time: number;
  volume: number;
  candles: { time: number; close: number }[];
  indicators: Record<string, number>;
};
type Position = {
  id: string;
  bot: string;
  product: string;
  qty: string;
  entry: string;
  cost: string;
  unrealized: string | null;
};
type Event = {
  id: string;
  bot: string;
  product: string;
  side: string;
  fill: string;
  pnl: string | null;
  fee: string;
  time: number;
  reasoning: string;
};
type State = {
  coinbase_connection?: {
    connected: boolean;
    secure_storage_available: boolean;
    saved: boolean;
  };
  live?: {
    enabled: boolean;
    cash: string;
    positions: { product: string; qty: string; cost: string }[];
    orders: {
      id: string;
      product: string;
      side: string;
      status: string;
      amount: string;
      filled_qty: string;
      requested_by: string;
    }[];
    unknown_execution: boolean;
  };
  token: string;
  cash: string;
  kill: boolean;
  auto: boolean;
  approval_policy: "human" | "automatic_paper";
  markets: Record<string, Market>;
  market_error: string;
  positions: Position[];
  proposals: Proposal[];
  journal: Event[];
  bots: { name: string; strategy: string; state: string; reasoning: string }[];
  performance: {
    max_drawdown: string | null;
    average: string | null;
    closed: number;
    net: string;
    win_rate: number | null;
    profit_factor: string | null;
    learning: string;
  };
};
const sections = [
  "3D Trading Floor",
  "Boss’s Office",
  "Bot Team",
  "Live Markets",
  "Paper Trading",
  "Live Trading",
  "Trade Proposals",
  "Manual Trading",
  "Bot Leaderboard",
  "Trade Journal",
  "Risk Management",
  "Settings",
];
const api = location.port === "1420" ? "/api" : "http://127.0.0.1:8765/api";
const money = (v: unknown) =>
  v === null || v === undefined
    ? "—"
    : new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: "USD",
        maximumFractionDigits: 2,
      }).format(Number(v));
class SceneBoundary extends Component<
  { children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? (
      <div className="scene-failed">
        3D rendering unavailable. Use the Bot Team and trading controls while
        checking WebGL support.
      </div>
    ) : (
      this.props.children
    );
  }
}
function Chart({ market }: { market: Market }) {
  const values = market.candles.map((c) => c.close),
    min = Math.min(...values),
    max = Math.max(...values);
  return (
    <svg
      viewBox="0 0 640 150"
      role="img"
      aria-label="Coinbase five minute closing price history"
    >
      <defs>
        <linearGradient id="fill" x2="0" y2="1">
          <stop stopColor="#59d5ba" stopOpacity=".25" />
          <stop offset="1" stopColor="#59d5ba" stopOpacity="0" />
        </linearGradient>
      </defs>
      {[30, 70, 110].map((y) => (
        <path key={y} d={`M0 ${y}H640`} stroke="#253440" />
      ))}
      <polyline
        fill="none"
        stroke="#65d6bc"
        strokeWidth="2"
        points={values
          .map(
            (v, i) =>
              `${(i / (values.length - 1)) * 640},${135 - ((v - min) / (max - min || 1)) * 120}`,
          )
          .join(" ")}
      />
    </svg>
  );
}
export default function App() {
  const [research, setResearch] = useState<{
    bot: string;
    status: string;
    training_candles: number;
    holdout_candles: number;
    assumptions: string;
    results: Record<
      string,
      {
        training: { trades: number; net: number };
        holdout: { trades: number; net: number };
      }
    >;
  } | null>(null);
  const [section, setSection] = useState(sections[0]),
    [selected, setSelected] = useState(0),
    [state, setState] = useState<State | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [product, setProduct] = useState("BTC-USD"),
    [amount, setAmount] = useState("5"),
    [preview, setPreview] = useState<Proposal | null>(null),
    [question, setQuestion] = useState(""),
    [answer, setAnswer] = useState("");
  async function load() {
    try {
      const r = await fetch(api + "/state");
      if (!r.ok) throw Error("Engine unavailable");
      setState(await r.json());
      setError("");
    } catch {
      setError(
        "Engine offline. Start python -m engine.server. Market data and trading are unavailable.",
      );
    }
  }
  useEffect(() => {
    void load();
    const timer = setInterval(() => void load(), 5000);
    return () => clearInterval(timer);
  }, []);
  async function action(path: string, data: object) {
    setBusy(true);
    try {
      const r = await fetch(api + path, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Nightshift-Token": state?.token || "",
        },
        body: JSON.stringify(data),
      });
      const result = await r.json();
      if (!r.ok) throw Error(result.error || "Request failed");
      await load();
      return result;
    } catch (e) {
      setError(String(e));
      return null;
    } finally {
      setBusy(false);
    }
  }
  const markets = state?.markets || {},
    pending = state?.proposals.filter((p) => p.status === "pending") || [],
    isFloor = section === sections[0] || section === sections[1];
  const proposalCard = (p: Proposal) => (
    <article className="proposal" key={p.id}>
      <div className="row">
        <span className="pill">{p.side.toUpperCase()} · PAPER</span>
        <span className="muted">{p.status}</span>
      </div>
      <h3>
        {p.product}{" "}
        <span>
          {money(p.side === "sell" ? p.estimated_notional : p.amount)}
        </span>
      </h3>
      <p>
        {p.bot} · {p.strategy_version}
        {p.side === "sell" &&
          ` · ${Number(p.amount).toPrecision(6)} ${p.amount_unit || "units"}`}
      </p>
      <div className="numbers">
        <span>
          Entry <b>{money(p.entry)}</b>
        </span>
        <span>
          Stop <b>{money(p.stop)}</b>
        </span>
        <span>
          Target <b>{money(p.target)}</b>
        </span>
        <span>
          Est. fee <b>{money(p.estimated_fee)}</b>
        </span>
      </div>
      <p>{p.reasoning}</p>
      <small>Confidence: uncalibrated · no profitability claim</small>
      <p>
        {p.origin === "manual"
          ? "Your ticket · reviewed by the team"
          : "Agent proposal · your approval is required in approval mode"}
      </p>
      {p.team_reviews && (
        <details className="team-reviews">
          <summary>Team review ({p.team_reviews.length} specialists)</summary>
          {p.team_reviews.map((review) => (
            <div className="review" key={review.bot}>
              <div className="row">
                <b>{review.bot}</b>
                <span className={review.opinion === "block" ? "fail" : "muted"}>
                  {review.opinion}
                  {review.binding ? " · mandatory risk gate" : " · advisory"}
                </span>
              </div>
              <p>{review.reason}</p>
            </div>
          ))}
        </details>
      )}
      {p.decision && (
        <p>
          Decision: {p.decision.approved ? "approved" : "rejected"} by{" "}
          {p.decision.actor.replaceAll("_", " ")} ·{" "}
          {new Date(p.decision.time * 1000).toLocaleString()}
        </p>
      )}
      <div className="checks">
        {p.checks.map((c) => (
          <div key={c.name} className={c.passed ? "pass" : "fail"}>
            {c.passed ? "✓" : "×"} {c.name}
          </div>
        ))}
      </div>
      {p.status === "pending" && (
        <div className="row">
          <button
            disabled={busy}
            onClick={() =>
              void action("/decide", { id: p.id, approve: true }).then(() =>
                setPreview(null),
              )
            }
          >
            Confirm paper order
          </button>
          <button
            className="ghost"
            disabled={busy}
            onClick={() =>
              void action("/decide", { id: p.id, approve: false }).then(() =>
                setPreview(null),
              )
            }
          >
            Reject
          </button>
        </div>
      )}
    </article>
  );
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <i>IV</i>
          <div>
            IRONTRADE<span>AI / NIGHTSHIFT</span>
          </div>
        </div>
        <div className="workspace-label">YOUR TRADING DESK</div>
        <nav>
          {sections.map((s, i) => (
            <button
              key={s}
              className={section === s ? "nav active" : "nav"}
              onClick={() => setSection(s)}
            >
              <span>
                {
                  [
                    "◈",
                    "▣",
                    "◉",
                    "⌁",
                    "▤",
                    "◇",
                    "▱",
                    "↗",
                    "▥",
                    "≡",
                    "⬡",
                    "⚙",
                  ][i]
                }
              </span>
              {s}
              {s === "Trade Proposals" && pending.length > 0 && (
                <em>{pending.length}</em>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <span className="dot" /> Local-first workspace
          <p>
            Paper capital · $25.00
            <br />
            Spot only. Risk always on.
          </p>
        </div>
      </aside>
      <main>
        <header>
          <div>
            <span className="eyebrow">THE MARKET NEVER SLEEPS</span>
            <h1>{section}</h1>
          </div>
          <div className="header-actions">
            <span className="pill">
              {state?.live?.enabled
                ? "LIVE ENABLED · APPROVAL REQUIRED"
                : "PAPER MODE"}
            </span>
            <button
              className={state?.kill ? "danger active" : "danger"}
              disabled={!state || busy}
              onClick={() => void action("/kill", { enabled: !state?.kill })}
            >
              {state?.kill ? "Resume entries" : "■ Emergency stop"}
            </button>
          </div>
        </header>
        {error && (
          <div className="alert" role="alert">
            {error}
          </div>
        )}
        <div className="ticker">
          {Object.entries(markets).length ? (
            Object.entries(markets).map(([p, q]) => (
              <div key={p}>
                <span>{p.replace("-USD", "")}</span>
                <b>{money(q.price)}</b>
                <small>
                  {Date.now() / 1000 - q.time < 90
                    ? "Coinbase REST"
                    : "STALE · NO ENTRIES"}
                </small>
              </div>
            ))
          ) : (
            <div>
              <span>MARKET FEED</span>
              <b>Awaiting verified prices</b>
              <small>No simulated market data</small>
            </div>
          )}
          <span className="ticker-note">5 MIN CANDLES · SPOT USD</span>
        </div>
        {isFloor ? (
          <>
            <section className="scene">
              <SceneBoundary>
                <Office
                  selected={selected}
                  onSelect={setSelected}
                  boss={section === sections[1]}
                />
              </SceneBoundary>
              <div className="scene-label">
                <span className="dot" /> NIGHTSHIFT / NEW YORK{" "}
                <p>Eight specialists. One risk mandate.</p>
              </div>
              <div className="scene-controls">
                Drag to orbit · Scroll to zoom · Select a trader
              </div>
              <div className="scene-time">
                OFFICE VISUALIZATION
                <span>Monitor graphics are illustrative</span>
              </div>
            </section>
            <div className="below-scene">
              <section className="agent-focus">
                <div className="row">
                  <div>
                    <span className="eyebrow">
                      WORKSTATION {String(selected + 1).padStart(2, "0")}
                    </span>
                    <h2 style={{ color: colors[selected] }}>
                      {names[selected]}
                    </h2>
                  </div>
                  <span className="pill subtle">
                    {state?.bots[selected]?.state || "OFFLINE"}
                  </span>
                </div>
                <p>
                  {state?.bots[selected]?.reasoning ||
                    "Waiting for the local engine and verified market evidence."}
                </p>
                <div className="row">
                  <button
                    className="ghost"
                    onClick={() => setSection("Bot Team")}
                  >
                    Inspect strategy ↗
                  </button>
                  <button onClick={() => setSection("Trade Proposals")}>
                    Review proposals ({pending.length})
                  </button>
                </div>
              </section>
              <section className="capital">
                <span className="eyebrow">PAPER PORTFOLIO</span>
                <h2>{money(state?.cash)}</h2>
                <p>Available cash · simulated capital</p>
                <div className="row">
                  <span>{state?.positions.length || 0} / 5 positions</span>
                  <span>Entry cap $5</span>
                </div>
              </section>
            </div>
            {section === sections[1] && (
              <section className="panel">
                <h2>Decision room</h2>
                <p>
                  Risk Officer: every entry is rechecked at execution. Wallet
                  Tracker: no verified on-chain feed; abstaining. Execution
                  Specialist: live orders require separate activation and your
                  individual approval.
                </p>
                <div className="grid">{pending.map(proposalCard)}</div>
              </section>
            )}
          </>
        ) : (
          <div className="content">
            {section === "Bot Team" && (
              <>
                <div className="grid">
                  {names.map((name, i) => (
                    <article className="panel" key={name}>
                      <span className="eyebrow" style={{ color: colors[i] }}>
                        AGENT / {i + 1}
                      </span>
                      <h2>{name}</h2>
                      <p>{state?.bots[i]?.strategy}</p>
                      <p>
                        {state?.bots[i]?.reasoning ||
                          "No market data available."}
                      </p>
                      <button
                        className="ghost"
                        onClick={() => {
                          setSelected(i);
                          setSection(sections[0]);
                        }}
                      >
                        Visit workstation ↗
                      </button>
                    </article>
                  ))}
                </div>
                <section className="panel">
                  <h2>Ask your team</h2>
                  <p>
                    Evidence-based local explanation. Conversational AI is not
                    connected.
                  </p>
                  <div className="row">
                    <input
                      aria-label="Question for the selected agent"
                      value={question}
                      onChange={(e) => setQuestion(e.target.value)}
                      placeholder="Ask about the current signal…"
                    />
                    <button
                      onClick={() =>
                        setAnswer(
                          question.trim()
                            ? `${names[selected]}: ${state?.bots[selected]?.reasoning || "No verified market evidence available."} This baseline agent can explain current indicators; open-ended AI chat is not yet enabled.`
                            : "Enter a question first.",
                        )
                      }
                    >
                      Ask {names[selected]}
                    </button>
                  </div>
                  <p aria-live="polite">{answer}</p>
                </section>
              </>
            )}
            {section === "Live Markets" && (
              <>
                {state?.market_error && (
                  <div className="alert">{state.market_error}</div>
                )}
                {Object.entries(markets).map(([p, q]) => (
                  <section className="panel" key={p}>
                    <div className="row">
                      <h2>{p}</h2>
                      <h2>{money(q.price)}</h2>
                    </div>
                    <Chart market={q} />
                    <div className="numbers">
                      <span>
                        Bid <b>{money(q.bid)}</b>
                      </span>
                      <span>
                        Ask <b>{money(q.ask)}</b>
                      </span>
                      <span>
                        RSI <b>{q.indicators.rsi.toFixed(1)}</b>
                      </span>
                      <span>
                        Source <b>Coinbase Exchange REST</b>
                      </span>
                    </div>
                    <small>
                      Exchange timestamp:{" "}
                      {new Date(q.time * 1000).toLocaleString()}
                    </small>
                  </section>
                ))}
                {!Object.keys(markets).length && (
                  <section className="panel">
                    <h2>Market data unavailable</h2>
                    <p>
                      Charts appear only after verified Coinbase candles arrive.
                      Check engine connectivity and network access to
                      api.exchange.coinbase.com.
                    </p>
                  </section>
                )}
              </>
            )}
            {section === "Paper Trading" && (
              <>
                <section className="panel">
                  <div className="row">
                    <div>
                      <h2>Paper trading lab</h2>
                      <p>
                        25 USD starting cash · 0.6% fee / side · spread + 5 bps
                        slippage
                      </p>
                    </div>
                    <button
                      disabled={!state || busy}
                      onClick={() =>
                        void action("/auto", { enabled: !state?.auto })
                      }
                    >
                      {state?.auto
                        ? "Pause paper agents"
                        : "Start paper agents"}
                    </button>
                  </div>
                  <p>
                    Agents scan every 30 seconds. By default, bot proposals wait
                    for your approval. Your manual tickets receive team review
                    and always require your confirmation. Paper exits monitor 2%
                    stop and 4% target levels every market refresh. Fresh quotes
                    and risk checks are still required; fills can slip beyond
                    these reference levels.
                  </p>
                </section>
                <section className="panel">
                  <h2>Trade alongside your team</h2>
                  <label>
                    Bot entry approval policy
                    <select
                      aria-label="Bot entry approval policy"
                      disabled={!state || busy}
                      value={state?.approval_policy || "human"}
                      onChange={(e) =>
                        void action("/approval-policy", {
                          policy: e.target.value,
                        })
                      }
                    >
                      <option value="human">
                        Ask me before every bot paper entry
                      </option>
                      <option value="automatic_paper">
                        Allow risk-approved automatic paper entries
                      </option>
                    </select>
                  </label>
                  <p>
                    Team opinions are advisory. The Risk Officer can block an
                    order; a bot cannot override your approval or risk limits.
                    Automatic protection may close owned paper positions at
                    stop/target levels. Live orders use a separate activation
                    and per-order confirmation workflow.
                  </p>
                  <button
                    className="ghost"
                    onClick={() => setSection("Trade Proposals")}
                  >
                    Review team proposals ({pending.length})
                  </button>
                </section>
                <Positions
                  positions={state?.positions || []}
                  close={(p) =>
                    void action("/propose", {
                      product: p.product,
                      amount: p.qty,
                      side: "sell",
                      position_id: p.id,
                    }).then((r) => r && setPreview(r))
                  }
                />
                {preview && proposalCard(preview)}
              </>
            )}
            {section === "Trade Proposals" && (
              <>
                <p className="muted">
                  Paper proposals only. Risk checks and prices are revalidated
                  on confirmation.
                </p>
                <div className="grid">{state?.proposals.map(proposalCard)}</div>
                {!state?.proposals.length && (
                  <section className="panel">
                    <h2>No proposals yet</h2>
                    <p>
                      Start paper agents or open a manual ticket to preview a
                      trade using verified prices.
                    </p>
                  </section>
                )}
              </>
            )}
            {section === "Manual Trading" && (
              <>
                <section className="panel ticket">
                  <span className="eyebrow">PAPER ORDER TICKET</span>
                  <h2>Make a deliberate move.</h2>
                  <p>
                    Available paper cash {money(state?.cash)} · use Live Trading
                    for Coinbase orders.
                  </p>
                  <label>
                    Spot asset
                    <select
                      value={product}
                      onChange={(e) => setProduct(e.target.value)}
                    >
                      {["BTC-USD", "ETH-USD", "SOL-USD"].map((p) => (
                        <option key={p}>{p}</option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Allocation including fee (USD)
                    <input
                      type="number"
                      min=".01"
                      max="5"
                      step=".01"
                      value={amount}
                      onChange={(e) => setAmount(e.target.value)}
                    />
                  </label>
                  <p>
                    Ask {money(markets[product]?.ask)} · estimated fee{" "}
                    {money(Number(amount) * 0.006)}
                  </p>
                  <button
                    disabled={!state || busy}
                    onClick={() =>
                      void action("/propose", {
                        product,
                        amount,
                        side: "buy",
                      }).then((r) => r && setPreview(r))
                    }
                  >
                    Preview paper buy →
                  </button>
                </section>
                {preview && proposalCard(preview)}
                <Positions
                  positions={state?.positions || []}
                  close={(p) =>
                    void action("/propose", {
                      product: p.product,
                      amount: p.qty,
                      side: "sell",
                      position_id: p.id,
                    }).then((r) => r && setPreview(r))
                  }
                />
              </>
            )}
            {section === "Live Trading" && (
              <CoinbasePanel
                connection={state?.coinbase_connection}
                live={state?.live}
                action={action}
                busy={busy}
                pending={pending}
              />
            )}
            {section === "Bot Leaderboard" && (
              <>
                <section className="panel">
                  <h2>Evidence before confidence.</h2>
                  <p>{state?.performance.learning}</p>
                  <div className="numbers">
                    <span>
                      Closed trades <b>{state?.performance.closed || 0}</b>
                    </span>
                    <span>
                      Net realized <b>{money(state?.performance.net)}</b>
                    </span>
                    <span>
                      Win rate{" "}
                      <b>
                        {state?.performance.win_rate == null
                          ? "—"
                          : (state.performance.win_rate * 100).toFixed(1) + "%"}
                      </b>
                    </span>
                    <span>
                      Profit factor{" "}
                      <b>{state?.performance.profit_factor || "—"}</b>
                    </span>
                    <span>
                      Average closed P/L{" "}
                      <b>{money(state?.performance.average)}</b>
                    </span>
                    <span>
                      Sampled maximum drawdown{" "}
                      <b>
                        {state?.performance.max_drawdown == null
                          ? "—"
                          : (
                              Number(state.performance.max_drawdown) * 100
                            ).toFixed(2) + "%"}
                      </b>
                    </span>
                  </div>
                </section>
                <section className="panel">
                  <h2>Champion / challenger research</h2>
                  <p>
                    Uses verified {product} candles. Each candidate is fixed
                    before holdout scoring. Limited samples do not prove
                    profitability.
                  </p>
                  <label>
                    Research market
                    <select
                      value={product}
                      onChange={(e) => {
                        setProduct(e.target.value);
                        setResearch(null);
                      }}
                    >
                      {["BTC-USD", "ETH-USD", "SOL-USD"].map((p) => (
                        <option key={p}>{p}</option>
                      ))}
                    </select>
                  </label>
                  <div className="row">
                    {[
                      "Market Scout",
                      "Technical Analyst",
                      "Momentum Maverick",
                      "Mean Reversion Quant",
                    ].map((bot) => (
                      <button
                        className="ghost"
                        key={bot}
                        disabled={!state || busy}
                        onClick={() =>
                          void action("/research", { bot, product }).then(
                            (r) => r && setResearch(r),
                          )
                        }
                      >
                        {bot}
                      </button>
                    ))}
                  </div>
                  {research && (
                    <>
                      <h3>{research.bot}</h3>
                      <p>
                        {research.status} Training: {research.training_candles}{" "}
                        candles; holdout: {research.holdout_candles} candles.
                      </p>
                      <div className="numbers">
                        {Object.entries(research.results).map(([name, r]) => (
                          <span key={name}>
                            {name}
                            <b>
                              {r.holdout.trades} holdout trades ·{" "}
                              {money(r.holdout.net)} net
                            </b>
                            Training {r.training.trades} trades ·{" "}
                            {money(r.training.net)}
                          </span>
                        ))}
                      </div>
                      <small>{research.assumptions}</small>
                    </>
                  )}
                </section>
                {names.map((name) => {
                  const trades =
                    state?.journal.filter(
                      (t) => t.bot === name && t.pnl !== null,
                    ) || [];
                  return (
                    <div className="leader" key={name}>
                      <b>{name}</b>
                      <span>{trades.length} closed paper trades</span>
                      <strong>
                        {money(trades.reduce((s, t) => s + Number(t.pnl), 0))}
                      </strong>
                    </div>
                  );
                })}
                <p className="muted">
                  Champion/challenger replay uses a chronological holdout and
                  next-observation fills. No learned strategy is active and
                  research cannot bypass risk controls.
                </p>
              </>
            )}
            {section === "Trade Journal" && (
              <section className="panel">
                <h2>Every decision leaves a trail.</h2>
                {state?.journal.length ? (
                  state.journal.map((t) => (
                    <article className="journal" key={t.id}>
                      <div className="row">
                        <b>
                          {t.side.toUpperCase()} {t.product} · {t.bot}
                        </b>
                        <span>{new Date(t.time * 1000).toLocaleString()}</span>
                      </div>
                      <p>
                        Paper fill {money(t.fill)} · fee {money(t.fee)} ·
                        realized {money(t.pnl)}
                      </p>
                      <p>{t.reasoning}</p>
                    </article>
                  ))
                ) : (
                  <p>No simulated fills recorded.</p>
                )}
              </section>
            )}
            {section === "Risk Management" && (
              <section className="panel">
                <span className="eyebrow">INDEPENDENT ENTRY GATE</span>
                <h2>Small capital. Strict boundaries.</h2>
                <div className="risk-grid">
                  {[
                    "$25 starting paper capital",
                    "$5 maximum entry, including fees",
                    "5 maximum open positions",
                    "2% realized + unrealized loss entry cutoff",
                    "90-second quote and proposal freshness",
                    "0.5% maximum quoted spread",
                    "Duplicate proposal execution rejected",
                    "Emergency stop prevents new entries",
                  ].map((s) => (
                    <div key={s}>✓ {s}</div>
                  ))}
                </div>
                <p>
                  Emergency stop does not liquidate positions. Full-position
                  paper exits require a fresh quote and explicit confirmation.
                  Paper stops are sampled every 30 seconds, require valid
                  quotes, and can slip beyond their reference levels. Every live
                  order requires individual human approval.
                </p>
              </section>
            )}
            {section === "Settings" && (
              <section className="panel">
                <h2>Local by design.</h2>
                <p>
                  Paper history is stored in SQLite by the local Python engine.
                  Start it with <code>python -m engine.server</code>. Use
                  IRONTRADE_DATA_DIR to choose a writable data directory.
                </p>
                <p>
                  Public market feed: api.exchange.coinbase.com. The Windows
                  desktop app links Coinbase accounts using user-bound encrypted
                  storage. This cloud browser does not accept private keys. Live
                  orders require separate activation and individual
                  confirmation. Ollama chat is not enabled.
                </p>
                <p>
                  Office assets are original procedural geometry. Current
                  characters have seated typing and head motion; walking and
                  production character assets remain in development.
                </p>
              </section>
            )}
          </div>
        )}
        <footer>
          <span>
            <span className="dot" />{" "}
            {state ? "LOCAL ENGINE CONNECTED" : "ENGINE OFFLINE"}
          </span>
          <span>
            {state?.live?.enabled
              ? "LIVE ENABLED · PER-ORDER HUMAN APPROVAL"
              : "PAPER MODE · LIVE DISABLED"}
          </span>
          <span>NIGHTSHIFT v0.1</span>
        </footer>
      </main>
    </div>
  );
}
function Positions({
  positions,
  close,
}: {
  positions: Position[];
  close: (p: Position) => void;
}) {
  return (
    <section className="panel">
      <h2>Open paper positions</h2>
      {positions.length ? (
        positions.map((p) => (
          <div className="leader" key={p.id}>
            <div>
              <b>{p.product}</b>
              <p>
                {p.bot} · {Number(p.qty).toPrecision(6)} units
              </p>
            </div>
            <span>Unrealized {money(p.unrealized)}</span>
            <button className="ghost" onClick={() => close(p)}>
              Preview full sell
            </button>
          </div>
        ))
      ) : (
        <p>No open positions.</p>
      )}
    </section>
  );
}
