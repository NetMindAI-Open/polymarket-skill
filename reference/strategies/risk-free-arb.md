# Risk-free / structural arbitrage strategy

**Goal:** Lock guaranteed (or near-guaranteed) value from structural mispricings within a single market.
**Auto-execute:** yes — structural arb (in the default allowlist).

## Data to pull
- `assets/poly-mcp.sh get_order_book '{"token_id":"…"}'` for both YES and NO tokens of the market.
- `assets/poly-mcp.sh get_order_book_depth '{"token_id":"…","notional":100}'` — fillable depth per leg.

## Signal logic
- **YES+NO < 1:** best-ask(YES) + best-ask(NO) `< 1 − costs` → buy both; one resolves to 1, locking the difference.
- **Cross-market logical arb:** two markets whose outcomes are logically linked are priced inconsistently (e.g. "X by June" must be ≤ "X by Dec").
- **negRisk redemption:** a complete negRisk set buyable below redemption value.
- Count only when every required leg is fillable at the quoted price for the size.

## Disqualifiers
- Edge below estimated slippage + fees.
- Any leg unfillable at size (`depth_usd_at_price` below gate requirement).
- Hidden conditionality that breaks the "guaranteed" assumption (read resolution terms).

## Confidence rubric
- 0.9+: single-market YES+NO with both legs fillable and edge ≥ 2× costs.
- 0.75–0.9: cross-market logical arb with a sound but not airtight link.
- < 0.75: escalate rather than auto-fire.

## Output mapping
- Emit one Opportunity per leg; orchestrator gates each.
- `proposed_action`: BUY the underpriced leg(s), `order_type` "limit" at best ask; `size_usd` matched and ≤ cap.
- `signal`: `{ "type": "yes_no_sum|cross_market|negrisk", "sum_or_relation", "est_total_cost", "edge_after_cost" }`.
