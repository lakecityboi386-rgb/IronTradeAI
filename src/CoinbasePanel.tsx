import { useState } from "react";
type Connection = {
  connected: boolean;
  secure_storage_available: boolean;
  saved: boolean;
};
type LiveState = {
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
  alerts?: { product: string; reason: string }[];
};
type Preview = {
  id: string;
  product: string;
  side: string;
  amount: string;
  approval_token: string;
  confirmation: string;
  team_reviews?: {
    bot: string;
    opinion: string;
    reason: string;
    binding: boolean;
  }[];
  preview: { estimated_fee: string; requested: Record<string, string> };
};
type Action = (path: string, data: object) => Promise<any>;
export default function CoinbasePanel({
  connection,
  live,
  action,
  busy,
  pending,
}: {
  connection?: Connection;
  live?: LiveState;
  action: Action;
  busy: boolean;
  pending: {
    id: string;
    product: string;
    bot: string;
    side: string;
    origin?: string;
  }[];
}) {
  const [notice, setNotice] = useState(""),
    [activation, setActivation] = useState(""),
    [product, setProduct] = useState("BTC-USD"),
    [budget, setBudget] = useState("5"),
    [preview, setPreview] = useState<Preview | null>(null),
    [confirmation, setConfirmation] = useState("");
  async function importKey(file: File | undefined) {
    if (!file) return;
    if (!connection?.secure_storage_available) {
      setNotice(
        "Link your account in the Windows desktop app. No credentials were sent.",
      );
      return;
    }
    if (file.size > 12000) {
      setNotice(
        "Key export is too large. Choose the Coinbase CDP JSON export.",
      );
      return;
    }
    try {
      const data = JSON.parse(await file.text());
      if (typeof data.name !== "string" || typeof data.privateKey !== "string")
        throw Error();
      const result = await action("/coinbase/connect", {
        api_key: data.name,
        api_secret: data.privateKey,
      });
      setNotice(
        result
          ? "Account verified and saved using Windows user-bound encryption. Live submission is still disabled."
          : "Account linking failed. No credential content is displayed or logged.",
      );
    } catch {
      setNotice(
        "Choose a valid Coinbase CDP API key JSON export. No credential content is displayed.",
      );
    }
  }
  async function makePreview(data: object) {
    setPreview(null);
    setConfirmation("");
    const result = await action("/live/preview", data);
    if (result) setPreview(result);
  }
  return (
    <>
      <section className="panel">
        <span className="eyebrow">PRIVATE COINBASE CONNECTION</span>
        <h2>Link your personal account</h2>
        <p>
          Your key is sent only to this app’s loopback engine for account
          verification. On Windows it is encrypted with DPAPI for your Windows
          user. It is never stored in browser storage, source code or logs.
          Coinbase receives signed API requests. Other programs running as your
          Windows user can still pose a risk; keep your device and exported key
          secure.
        </p>
        <p>
          Create a Coinbase CDP API key with View and Trade permissions and no
          Transfer permission. Use an ECDSA key supported by the Advanced Trade
          SDK. Import its JSON export below; do not paste keys into chat.
        </p>
        {!connection?.secure_storage_available && (
          <div className="alert">
            Account linking is unavailable in this Linux/cloud browser. Import
            is disabled here. Use the Windows desktop app for user-bound
            encrypted storage.
          </div>
        )}
        <label>
          Coinbase key JSON export
          <input
            aria-label="Coinbase key JSON export"
            type="file"
            accept=".json,application/json"
            disabled={busy || !connection?.secure_storage_available}
            onChange={(e) => {
              const f = e.target.files?.[0];
              e.target.value = "";
              void importKey(f);
            }}
          />
        </label>
        <p role="status">{notice}</p>
        <div className="row">
          <span className="pill">
            {connection?.connected ? "ACCOUNT VERIFIED" : "NOT CONNECTED"}
          </span>
          {(connection?.connected || connection?.saved) && (
            <button
              className="ghost"
              disabled={busy}
              onClick={() =>
                void action("/coinbase/disconnect", {}).then(() => {
                  setPreview(null);
                  setNotice(
                    "Disconnected. Saved encrypted credentials removed. Existing submitted orders are not cancelled.",
                  );
                })
              }
            >
              Unlink and remove saved key
            </button>
          )}
        </div>
      </section>
      <section className="panel">
        <h2>Deliberate live activation</h2>
        <p>
          Live allocation $25 · entry cap $5 including estimated fees · five
          positions · 2% daily loss cutoff. Every live order, including
          protective exits and bot recommendations, needs your individual
          confirmation. Live activation resets when the engine restarts. The
          entry kill switch does not cancel existing orders.
        </p>
        {live?.enabled ? (
          <button
            className="danger"
            disabled={busy}
            onClick={() =>
              void action("/live/deactivate", {}).then(() => setPreview(null))
            }
          >
            Disable live submission
          </button>
        ) : (
          <>
            <label>
              Type ENABLE LIVE TRADING
              <input
                aria-label="Live activation confirmation"
                autoComplete="off"
                value={activation}
                onChange={(e) => setActivation(e.target.value)}
              />
            </label>
            <button
              disabled={
                busy ||
                !connection?.connected ||
                activation !== "ENABLE LIVE TRADING"
              }
              onClick={() =>
                void action("/live/activate", {
                  confirmation: activation,
                }).then(() => setActivation(""))
              }
            >
              Enable individually approved live orders
            </button>
          </>
        )}
        <p>
          Tracked live cash: ${Number(live?.cash ?? 25).toFixed(2)}. This is
          NightShift’s separate allocation ledger, not your full Coinbase
          account balance.
        </p>
        {live?.unknown_execution && (
          <div className="alert">
            An execution is unresolved. Entries are blocked. Reconcile the
            original order; do not submit a replacement.
          </div>
        )}
      </section>
      {live?.enabled && (
        <section className="panel">
          <h2>Live order ticket</h2>
          <label>
            Product
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
            Maximum buy budget including estimated fee (USD)
            <input
              type="number"
              min="1"
              max="5"
              step=".01"
              value={budget}
              onChange={(e) => setBudget(e.target.value)}
            />
          </label>
          <button
            disabled={busy || live.unknown_execution}
            onClick={() =>
              void makePreview({ product, side: "buy", amount: budget })
            }
          >
            Get Coinbase buy preview
          </button>
          <h3>Bot recommendations</h3>
          <p>
            Choosing a bot proposal creates a live broker preview. It does not
            submit the proposal.
          </p>
          {pending
            .filter((p) => p.origin === "agent" && p.side === "buy")
            .map((p) => (
              <div className="leader" key={p.id}>
                <span>
                  {p.bot} · {p.product}
                </span>
                <button
                  className="ghost"
                  disabled={busy}
                  onClick={() => void makePreview({ proposal_id: p.id })}
                >
                  Review live preview
                </button>
              </div>
            ))}
          <h3>Owned live positions</h3>
          {live.alerts?.map((a) => (
            <div className="alert" key={a.product}>
              {a.product}: {a.reason}
            </div>
          ))}
          {live.positions.map((p) => (
            <div className="leader" key={p.product}>
              <span>
                {p.product} · {p.qty} units
              </span>
              <button
                className="ghost"
                disabled={busy}
                onClick={() =>
                  void makePreview({
                    product: p.product,
                    side: "sell",
                    amount: p.qty,
                  })
                }
              >
                Preview full live sell
              </button>
            </div>
          ))}
        </section>
      )}
      {preview && (
        <section className="panel">
          <span className="pill">REAL MONEY · FINAL CONFIRMATION</span>
          <h2>
            {preview.side.toUpperCase()} {preview.product}
          </h2>
          <p>
            Amount: {preview.amount}{" "}
            {preview.side === "buy" ? "USD maximum budget" : "base units"} ·
            estimated fee ${preview.preview.estimated_fee}. Preview expires
            after 30 seconds. Changed fees or sizing require a new approval.
            Market prices can move; actual execution fees and loss may differ
            from estimates.
          </p>
          {preview.team_reviews && (
            <details className="team-reviews">
              <summary>Team review of this live ticket</summary>
              {preview.team_reviews.map((r) => (
                <div className="review" key={r.bot}>
                  <b>
                    {r.bot} · {r.opinion}
                    {r.binding ? " · mandatory gate" : " · advisory"}
                  </b>
                  <p>{r.reason}</p>
                </div>
              ))}
            </details>
          )}
          <label>
            Type exactly: {preview.confirmation}
            <input
              aria-label="Individual live order confirmation"
              autoComplete="off"
              value={confirmation}
              onChange={(e) => setConfirmation(e.target.value)}
            />
          </label>
          <div className="row">
            <button
              className="danger"
              disabled={busy || confirmation !== preview.confirmation}
              onClick={async () => {
                const p = preview;
                setPreview(null);
                setConfirmation("");
                await action("/live/approve", {
                  id: p.id,
                  approval_token: p.approval_token,
                  confirmation,
                });
              }}
            >
              Submit this live order once
            </button>
            <button className="ghost" onClick={() => setPreview(null)}>
              Reject preview
            </button>
          </div>
        </section>
      )}
      <section className="panel">
        <h2>Live execution journal</h2>
        <p>
          Reconciliation is read-only and remains available after deactivation.
          A timeout retains the original client order ID and capital
          reservation.
        </p>
        {live?.orders.map((o) => (
          <div className="leader" key={o.id}>
            <div>
              <b>
                {o.side.toUpperCase()} {o.product} · {o.status}
              </b>
              <p>
                {o.requested_by} · filled {o.filled_qty} units
              </p>
            </div>
            {["OPEN", "PENDING", "QUEUED", "CANCEL_QUEUED"].includes(
              o.status,
            ) && (
              <button
                className="danger"
                disabled={busy || !connection?.connected}
                onClick={() => {
                  if (
                    window.confirm(
                      "Request cancellation of this original live order? A fill may still occur until cancellation is reconciled.",
                    )
                  )
                    void action("/live/cancel", {
                      id: o.id,
                      confirmation: "CANCEL " + o.id,
                    });
                }}
              >
                Request cancellation
              </button>
            )}
            {o.status !== "PREVIEW" && (
              <button
                className="ghost"
                disabled={busy || !connection?.connected}
                onClick={() => void action("/live/reconcile", { id: o.id })}
              >
                Reconcile original order
              </button>
            )}
          </div>
        ))}
      </section>
    </>
  );
}
