# Risk-free / structural arbitrage strategy

**Goal:** Lock guaranteed (or near-guaranteed) value from structural mispricings within a single market.
**Auto-execute:** yes — structural arb (in the default allowlist).

## Data to pull
- **Shortlist first, from the shared universe — never enrich while scanning.** Using only fields already on each row (best_bid/ask, spread, liquidity, token ids for YES and NO, event_id, etc.), pick the markets where a structural edge is plausible: best-ask(YES)+best-ask(NO) already near/below 1, tight two-sided books, or events whose markets are logically linked (cross-market) / form a negRisk set. This fan-out is the heaviest in the suite (`get_order_book` for YES AND NO of every shortlisted market, plus `get_order_book_depth` per leg → ~2–3 calls × many markets, often 100+ books), so the shortlist must be aggressive before any enrichment.
- **Then gather enrichment for ONLY the shortlist in ONE batched pass — never loop single `poly-mcp.sh <tool>` calls (each pays a ~5s handshake).**
  - `get_order_book` — full book per token, for both YES and NO of each shortlisted market (best-ask sum, cross-market relation, negRisk set price).
  - `get_order_book_depth` (`{"notional":100}`) — fillable depth per leg, to confirm each leg fills at the quoted price for the intended size.
  - Prefer the native `mcp__polymarket__*` tools when reachable (one persistent session, sub-second calls, no per-call handshake).
  - Otherwise use ONE `poly-mcp.sh --batch` pass: NDJSON in on stdin, one object per line `{"id":"<token_id>:<tool>","tool":"get_order_book|get_order_book_depth","args":{…}}`; NDJSON out on stdout `{"id":…,"ok":true,"result":{…}}` (a per-call `{"ok":false,"error":…}` does not abort the batch). The `id` joins each book/depth back to its token, market, and leg.
  - Because the fan-out is large (many tokens × 2 tools), **shard the calls across ~4 parallel `poly-mcp.sh --batch` invocations** to hide the ~2s/call server-side latency (e.g. a 48-call enrichment dropped from >120s looping to ~30s across 4 shards).
- Any `poly -o json data positions <addr>` checks are poly-CLI calls, not MCP — keep them separate; they are not part of the `--batch` NDJSON.

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
