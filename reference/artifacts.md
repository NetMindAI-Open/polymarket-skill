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

```js
const DATA = {
  meta: { generated_at: "<UTC ISO>", wallet_label: "deposit 0x…", currency: "USDC" },

  markets: [{                       // Tab A — one entry per market to surface
    question, slug, condition_id, yes_token_id, no_token_id,
    url,                            // optional — "Trade on Polymarket" + modal "View on Polymarket"; falls back to /event/<slug>
    category,                       // optional — "Sports"|"Politics"|"Crypto"|"Tech"|"Finance"|"Weather"|"Other" → filter chips + tag
    end_date,                       // optional — ISO date; powers the time-left badge ("6mo left"/"Ended") + "Ending Soon" sort
    liquidity,                      // optional — stats strip + sort + modal
    volume_total,                   // optional — modal "Total Volume" + "Total Volume" sort (falls back to volume_24h)
    description,                    // optional — resolution text shown in the click-through detail modal
    trending,                       // optional — true if merged from the 24h-popularity list (build_data.py); tags the card, and lacking a real category gets a "🔥 Trending" filter chip
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
    rationale,                      // one or two sentences
    signals: ["net_flow +45k/24h", "spread 2¢"],  // monospace chips
    // optional — from an opportunity-scan run (see build_data.py):
    status,                         // "executed" | "pending" | "skipped"  → status pill
    strategy,                       // e.g. "risk-free-arb"  → meta line
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
| `markets[].trending` | the 24h-popularity merge in `build_data.py` (rows from `run.json.trending`, ranked by 24h volume) |
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
  "generated_at": "<UTC ISO>", "wallet_label": "deposit 0x…", "top_n": 24, "trending_n": 12,
  "universe": [ /* the merged scout universe rows (Step 1) */ ],
  "trending": [ /* a separate broad pull ranked by 24h volume (popularity, NOT the anomaly screens); same row shape as universe */ ],
  "opportunities": [ /* validated opportunities, each with the gate result attached:
                        "gate": {"decision":"auto"|"escalate"|"skip", "order_id": "<if filled>"} */ ],
  "enrichment": { "<condition_id>": { "url", "category", "end_date", "description",
                                      "volume_total", "net_flow", "depth", "candles" } },
  "account": { /* artifacts.md Account shape, or null */ }
}
```

What the mapper does:
- **Curated subset** — `markets[]` = every recommended market **+** the top-`top_n` universe rows by
  24h volume (deduped). Enrich only this subset with `candles`/`depth`/etc. via the MCP — never all
  50–150, or the payload explodes.
- **Trending merge** — `markets[]` is then enriched with the top-`trending_n` of the `trending` list
  (a broad, by-24h-volume pull — popularity, *not* the anomaly screens), deduped by `condition_id` and
  tagged `trending: true`. A hot market with no real `category` gets `category: "🔥 Trending"` so the
  template's category chip/tag surfaces it (no template change). `screen_markets` has no raw-volume
  sort, so pull a broad set (e.g. `sort_by="liquidity"`, high `limit`) and rank it by `volume_24h`.
- **Opportunity → recommendation** mapping:

  | Opportunity | → recommendation | rule |
  |---|---|---|
  | `gate.decision` auto/escalate/skip | `status` executed/pending/skipped | status pill |
  | `proposed_action.side` | `action` | `WATCH` if skipped, else the side |
  | `proposed_action.price` / `size_usd` | `target_price` / `size_usd` | passthrough |
  | `confidence` (0–1) | `confidence_score` + `confidence` band | ≥0.75 high · ≥0.5 medium · else low |
  | `thesis` | `rationale` | passthrough |
  | `strategy`, `edge_estimate` | `strategy`, `edge` | passthrough |
  | `gate.order_id` | `order_id` | shown when executed |
  | `liquidity_check` + `signal` + `risks` | `signals[]` | composed chips |
  | — (joined from universe by `condition_id`) | `question` | Opportunity has no title |
  | `enrichment[cond].url` | `url` | **real event slug** so the link resolves |

- **`meta.stats`** is summed from the **full** universe (not the injected subset), so the stats strip
  reflects everything scanned.

**You still must fetch the enrichment** (event slug + category/end_date/description from Gamma; `depth`
+ `candles` from the MCP) for the curated subset and pass it in — the mapper is pure and does no I/O.

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
