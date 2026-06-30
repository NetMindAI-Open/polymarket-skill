# Multi-outcome arbitrage strategy

**Goal:** In a mutually-exclusive multi-outcome event, exploit the YES prices summing to ≠ 100%.
**Auto-execute:** yes — structural arb (in the default allowlist).

## Data to pull
First shortlist from the shared universe: pick candidate **events** whose sibling rows (already carrying `event_id`, YES `token_id`s, `best_bid`/`best_ask`, `spread`, `liquidity`) hint that the basket's best-ask YES prices sum away from 1. Only then enrich that shortlist — never enrich every event as you scan. Tools needed (HOW to call them, not which):
- `list_markets` (args `{"event_id":"…"}`) — all sibling markets/outcomes in the event.
- `get_order_book` (args `{"token_id":"…"}`) per outcome's YES — real fillable prices, not mid.
- `get_order_book_depth` (args `{"token_id":"…","notional":100}`) — depth at the executable price.

Call them in ONE batched pass, not a per-token loop (each `poly-mcp.sh <tool>` spawn pays a ~5s handshake):
- Prefer native `mcp__polymarket__*` tools when reachable — one persistent session, sub-second calls, no per-call handshake.
- Otherwise pipe NDJSON into a single `assets/poly-mcp.sh --batch`: one line per call `{"id":"<event>:<token>:<tool>","tool":"get_order_book","args":{…}}`; read NDJSON back `{"id":…,"ok":true,"result":{…}}` (a failed leg → `{"ok":false,"error":…}` without aborting the batch). The `id` joins each book/depth back to its outcome leg.
- This fan-out is wide — every sibling YES needs both an order book and a depth call, so a long event makes a large batch. Shard across ~4 parallel `poly-mcp.sh --batch` invocations to also hide the ~2s/call server latency (a 48-call run drops from >120s timing out to ~30s). See reference/mcp.md "Speed: never loop single calls".

## Signal logic
- Sum of best-ask YES prices across all mutually-exclusive outcomes `< 1 − fees/slippage` → buy the basket (each YES) to lock a gain at resolution.
- Or sum of best-bid YES prices `> 1 + costs` → sell the basket.
- Only count it if each leg is **fillable** at the quoted price for the intended size.

## Disqualifiers
- Outcomes not actually mutually exclusive / collectively exhaustive (read the event carefully).
- Edge smaller than estimated total slippage + any fees.
- Any leg too thin to fill (`depth_usd_at_price` below the gate's requirement).

## Confidence rubric
- 0.9+: complete outcome set, all legs fillable, edge ≥ 2× estimated costs.
- 0.75–0.9: edge positive but thinner margin over costs.
- < 0.75: do not auto-execute (escalate) — edge too close to costs.

## Output mapping
- Emit one Opportunity **per leg** (each YES leg to buy), sharing the basket thesis; the orchestrator gates each leg.
- `proposed_action`: BUY YES, `order_type` "limit" at the leg's best ask; `size_usd` matched across legs and ≤ cap.
- `signal`: `{ "sum_of_outcomes", "legs", "est_total_cost", "edge_after_cost" }`.
