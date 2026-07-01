# Artifacts — the dashboard template

How to turn live Polymarket data into the visual **dashboard artifact**
([`assets/dashboard-template.html`](../assets/dashboard-template.html)).

The artifact is **sandboxed HTML**: it cannot run `poly`, cannot call the MCP, and cannot make network
requests. So you fetch the data here, normalize it into one `DATA` object, **inject** it into the
template, and emit the result. The dashboard is a **frozen snapshot** — there is no live refresh.

---

## Procedure

1. **Fetch** only what the user asked to see (skip sections you don't need):
   - **Markets** — `poly -o json markets get/search` for `question/slug/condition_id/yes_token_id/yes_price`.
     Enrich each with the polymarket MCP (optional but recommended):
     `get_order_book_depth(token_id=<yes_token_id>)` → `depth`,
     `get_price_history(token_id=<yes_token_id>)` → `candles` (map each candle's
     `open/high/low/close/volume` → `{o,h,l,c,v}`; renders as candlesticks + a volume strip),
     `get_market_stats(condition_id=…)` → `volume_24h`, `net_flow`.
     For the explorer (category chips, search, sort, time-left badges, click-through detail
     modal), also fill the optional `category` / `end_date` / `liquidity` / `volume_total` /
     `description` per market. The Markets tab filters/sorts entirely client-side on the snapshot.
   - **Recommendations** — your own analysis. Fill each with `outcome`, `action`, `target_price`,
     `confidence`, a cited `rationale`, and `signals[]`. No single data source.
   - **Account** — gather only when the wallet is set up (check `wallet show` first): `clob balance
     --asset-type collateral`, `data value`, `data positions`, `clob orders`, `clob trades`, `wallet show`.
     **No key / not set up → set `account: null`**; the Account tab then renders wallet-setup steps, and the
     markets/recommendations tabs still work with no wallet.
2. **Build** the `DATA` object (schema below). Keep every number as the **Decimal string** the source
   returns (`"0.67"`, not `0.67`). Stamp `meta.generated_at` with the current UTC ISO timestamp.
3. **Inject** — read `assets/dashboard-template.html`, replace **only** the block between
   `POLYMARKET_DATA_START` and `POLYMARKET_DATA_END` with your `const DATA = {…};`, and emit the whole
   file as the artifact. Change nothing else.
4. **Caveat** the user: the dashboard is frozen at `generated_at`; ask them to say "refresh my
   Polymarket dashboard" (or click ↻ regenerate) to rebuild with fresh data.

**Empty-state rule:** any list you don't fill → `[]`; any object you skip → `null`. Never omit a key —
the template renders an explicit empty state ("No order book"; a null `account` → wallet-setup steps) instead of breaking.

---

## DATA schema

**Bilingual (zh/en):** the dashboard ships both languages and toggles instantly via the header `中/EN`
control, **defaulting to Chinese**. UI chrome is translated inside the template; *data* prose that you
author — `rationale` and each `signals`/risk entry, plus `strategy_note`/`gate_note` — may be a plain
string (same in both languages) **or** a bilingual object `{ "en": "…", "zh": "…" }`. Trading terms
(`BUY/SELL/WATCH`, `HIGH/MEDIUM/LOW`, `YES/NO`) and market `question` titles stay English by design.

```js
const DATA = {
  meta: { generated_at: "<UTC ISO>", wallet_label: "deposit 0x…", currency: "USDC",
          lang: "zh" },              // default dashboard language ("zh" | "en"); user can still toggle

  markets: [{                       // Tab A — one entry per market to surface
    question, slug, condition_id, yes_token_id, no_token_id,
    url,                            // optional — "Trade on Polymarket" + modal "View on Polymarket"; falls back to /event/<slug>
    category,                       // optional — "Sports"|"Politics"|"Crypto"|"Tech"|"Finance"|"Weather"|"Other" → filter chips + tag
    end_date,                       // optional — ISO date; powers the time-left badge ("6mo left"/"Ended") + "Ending Soon" sort
    liquidity,                      // optional — stats strip + sort + modal
    volume_total,                   // optional — modal "Total Volume" + "Total Volume" sort (falls back to volume_24h)
    description,                    // optional — resolution text shown in the click-through detail modal
    yes_price,                      // "0.67"  (probability = ×100)
    volume_24h, net_flow,           // optional, MCP get_market_stats ("" or omit→hidden)
    depth: { bids:[[price,size,cum]], asks:[[price,size,cum]] },  // MCP get_order_book_depth, ~6 levels/side; [] if none
    candles: [{o,h,l,c,v}, …]       // MCP get_price_history OHLCV, oldest→newest, ~20-40 bars; [] if none
    // (fallback: sparkline: ["0.61","0.62", …] — closes only, renders a line if you have no OHLC)
  }],

  recommendations: [{               // Tab B — your analysis / scanner output
    question, slug,
    url,                            // optional — "View on Polymarket" link on the card (real event slug)
    outcome,                        // "YES" | "NO"
    action,                         // "BUY" | "SELL" | "HOLD" | "WATCH"  (drives badge color)
    target_price,                   // "0.67"
    confidence,                     // "high" | "medium" | "low"  (badge + meter color)
    confidence_score,               // "0.78"  (0–1, fills the meter)
    rationale,                      // one or two sentences — string OR {en,zh}
    signals: ["net_flow +45k/24h", "spread 2¢"],  // monospace chips; each entry string OR {en,zh}
    // optional — from an opportunity-scan run (see build_data.py):
    status,                         // "executed" | "pending" | "skipped"  → status pill
    strategy,                       // e.g. "risk-free-arb"  → meta line
    strategy_note,                  // gloss of the play → line under the meter (every card); {en,zh} from build_data
    gate_note,                      // skipped only — "why set aside" → amber aside box; {en,zh} from build_data
    size_usd,                       // proposed order size  → meta line
    edge,                           // e.g. "~3%"            → meta line
    order_id                        // filled order id (when status="executed")  → footer
  }],

  account: {                        // Tab C — poly CLI; set the whole object null if no key
    wallet:  { signer_eoa, deposit_wallet, note },          // wallet show (api_wallet → deposit_wallet)
    balance: { cash, raw },                                 // clob balance --asset-type collateral
    value:   { total, user },                               // map from `data value` → [{user, value}]: total = [0].value
    positions: [{ title, outcome, size, avg_price, cur_price, current_value, cash_pnl, percent_pnl }], // data positions
    orders:    [{ id, side, outcome, price, original_size, size_matched, status }],                     // clob orders
    trades:    [{ matched_at, side, outcome, price, size, status }]                                     // clob trades
  }
};
```

### Source map

| DATA path | Origin |
|---|---|
| `markets[].{question,slug,condition_id,yes_token_id,no_token_id,yes_price}` | `poly -o json markets get/search` **or** MCP `search_markets`/`get_market` |
| `markets[].url` | the market's Polymarket page → `https://polymarket.com/event/<event-slug>` (powers the "Trade on Polymarket" button; optional — template builds `/event/<slug>` if omitted, and only renders real `polymarket.com` links) |
| `markets[].{volume_24h,net_flow}` | MCP `get_market_stats(condition_id)` |
| `markets[].depth` | MCP `get_order_book_depth(token_id=yes_token_id)` — `[price,size,cumulative]`, trim ~6 levels/side |
| `markets[].candles` | MCP `get_price_history(token_id=yes_token_id)` → `{o,h,l,c,v}` per candle (open/high/low/close/volume) |
| `markets[].category` | classify the market (or read the event tag); drives the category filter chips + the on-card tag |
| `markets[].end_date` | the market's resolution/close date (ISO); drives the time-left badge and the "Ending Soon" sort |
| `markets[].liquidity` | MCP `get_market` / `get_market_stats` (or Gamma) — total book liquidity |
| `markets[].volume_total` | lifetime volume (Gamma `volume` / `get_market`); modal "Total Volume" + sort |
| `markets[].description` | the market's resolution criteria text (Gamma `description`); shown in the detail modal |
| `meta.stats` (optional) | `{total_volume, volume_24h, liquidity, active}` to override the stats strip; omit and the template sums them from `markets[]` |
| `recommendations[]` | your analysis, **or** an opportunity-scan run mapped by `assets/build_data.py` (see below) |
| `account.wallet` | `poly -o json wallet show` (`api_wallet` → `deposit_wallet`) |
| `account.balance` | `poly -o json clob balance --asset-type collateral` (`balance` → `cash`) |
| `account.value.total` | `poly -o json data value` → **returns `[{user, value}]`** (a list, field `value`), so `total = result[0].value`. The template also falls back to summing `positions[].current_value` if `total` is missing/0. |
| `account.positions` / `orders` / `trades` | `poly -o json data positions` / `clob orders` / `clob trades` (pass through) |

---

## From an opportunity-scan run (orchestration → artifact)

When the artifact is the visual output of the [orchestration playbook](orchestration.md),
**don't hand-build `DATA`** — let `assets/build_data.py` map the run deterministically. It takes
the scan's universe + gated opportunities + per-market enrichment (+ account) and emits the filled
HTML:

```bash
python3 assets/build_data.py --inject assets/dashboard-template.html < run.json > dashboard.html
```

`run.json` (you assemble it from the run):

```jsonc
{
  "lang": "zh",                       // default dashboard language ("zh" default | "en") -> meta.lang
  "generated_at": "<UTC ISO>", "wallet_label": "deposit 0x…",
  "universe": [ /* the active-markets pool; the Markets tab is its top 50 rows by 24h volume */ ],
  "opportunities": [ /* every gated opportunity — auto, escalate AND skip — each with the gate result:
                        "gate": {"decision":"auto"|"escalate"|"skip", "reason":"…", "order_id": "<if filled>"};
                        thesis + each risks entry may be a string OR bilingual {"en":"…","zh":"…"} */ ],
  "enrichment": { "<condition_id>": { "url", "category", "end_date", "description",
                                      "volume_total", "net_flow", "depth", "candles" } },
  "account": { /* artifacts.md Account shape, or null */ }
}
```

What the mapper does:
- **Markets tab** — `markets[]` = the **top `MARKETS_LIMIT` (50) `universe` rows by 24h volume**, with
  dead markets (YES `≤ MIN_YES_PRICE`, 0.01 = 1%) dropped first. That's the whole rule: just the most-
  traded markets in the last 24h. (Fewer than 50 live rows in the pool → show all of them.) Recommendations
  are a **separate tab** and are **not** merged into this grid. Enrich only these shown markets with
  `candles`/`depth`/etc. via the MCP — never all 50–150, or the payload explodes. `screen_markets` has no
  raw-volume sort, so build the `universe` pool from a broad pull (e.g. `sort_by="liquidity"`, high `limit`)
  and `build_data.py` ranks it by `volume_24h` and takes the top 50.
- **Opportunity → recommendation** mapping:

  | Opportunity | → recommendation | rule |
  |---|---|---|
  | `gate.decision` auto/escalate/skip | `status` executed/pending/skipped | status pill |
  | `proposed_action.side` | `action` | `WATCH` if skipped, else the side |
  | `proposed_action.price` / `size_usd` | `target_price` / `size_usd` | passthrough |
  | `confidence` (0–1) | `confidence_score` + `confidence` band | ≥0.75 high · ≥0.5 medium · else low. **Skip → forced `low` band** with a small fixed UX meter (3 bars if raw conf ≥0.5, else 2) rather than the raw score |
  | `thesis` | `rationale` | passthrough (string or `{en,zh}`) — *why this market is a candidate* |
  | `strategy`, `edge_estimate` | `strategy`, `edge` | passthrough |
  | `strategy` | `strategy_note` | **bilingual** `{en,zh}` gloss from `STRATEGY_NOTES` — *what the play is* (every card) |
  | `gate.reason` (skip only) | `gate_note` | **bilingual** `{en,zh}` from `GATE_REASON_NOTES` — *why it was set aside* (amber aside box); unknown codes wrapped verbatim |
  | `gate.order_id` | `order_id` | shown when executed |
  | `liquidity_check` + `signal` + `risks` | `signals[]` | composed chips — **risks** live here (each may be string or `{en,zh}`) |
  | — (joined from universe by `condition_id`) | `question` | Opportunity has no title |
  | `enrichment[cond].url` | `url` | **real event slug** so the link resolves |

- **`meta.stats`** is summed from the **full** universe (not the injected subset), so the stats strip
  reflects everything scanned.

**You still must fetch the enrichment** (event slug + category/end_date/description from Gamma; `depth`
+ `candles` from the MCP) for the 50 shown markets and pass it in — the mapper is pure and does no I/O.
Fetch it fast: **one batched Gamma `curl`** (`condition_ids=a&condition_ids=b&…`) for all the metadata,
and **native `mcp__polymarket__*` tools or one `poly-mcp.sh --batch` pass** for depth/candles/stats —
never a per-call `poly-mcp.sh` loop (it re-pays the ~5s handshake each time). See
[mcp.md](mcp.md#speed-never-loop-single-calls--go-native-or-batch).

---

## Risks & caveats

- **Snapshot staleness** — odds and balances are frozen at `generated_at`; there is no in-artifact live
  refresh. Always tell the user, and regenerate on request.
- **Sandbox can't fetch** — if you forget to inject `DATA`, the dashboard shows a "No data injected"
  banner. Always replace the placeholder block.
- **Account needs a key** — without a configured, funded, activated wallet the Account tab renders
  wallet-setup steps instead of balances. Never echo the private key; if there's no key, set
  `account: null` (markets/recs still render).
- **Use the MARKET token id** — `depth`/`candles` are keyed by the market's `yes_token_id`, not an
  *event* id (see the "event slug ≠ market slug" note in [../SKILL.md](../SKILL.md)).
- **Trade link** — set `url` to the real Polymarket page `https://polymarket.com/event/<event-slug>`,
  using the canonical **event slug** (e.g. Gamma API `https://gamma-api.polymarket.com/events…` →
  `events[].slug`, or the market's share URL). A *market* slug or an invented slug **404s** — the
  template validates the domain (`polymarket.com`) but can't check the slug exists, so a wrong slug
  still renders a button that leads nowhere. If you can't get the real event slug, omit both `url` and
  `slug` so no broken link shows (the card/modal then say "no Polymarket link").
- **Payload size** — trim `depth` to ~6 levels/side and `candles` to ~20–40 bars so the injected
  `DATA` stays small and renders fast.
- **Keep Decimal strings** — inject the strings the sources emit; the template `parseFloat`s at render.
  Don't pre-round or convert to numbers, or you lose source precision.

## Verify a build

Open the filled file in a browser (or the launch preview). Check: each tab renders; Markets cards show
candlesticks + a volume strip + depth ladder (and a clean empty state for a market with no book or no
candles); Account tables populate and
**sort** on header click without disturbing other tabs; the browser console shows **zero** errors and
**zero** network requests. The unfilled template ships with sample data so it always renders standalone.
