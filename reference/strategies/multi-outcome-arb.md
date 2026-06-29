# Multi-outcome arbitrage strategy

**Goal:** In a mutually-exclusive multi-outcome event, exploit the YES prices summing to ≠ 100%.
**Auto-execute:** yes — structural arb (in the default allowlist).

## Data to pull
- `assets/poly-mcp.sh list_markets '{"event_id":"…"}'` — all markets in the event.
- `assets/poly-mcp.sh get_order_book '{"token_id":"…"}'` for each outcome's YES — real fillable prices, not mid.
- `assets/poly-mcp.sh get_order_book_depth '{"token_id":"…","notional":100}'` — depth at the executable price.

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
