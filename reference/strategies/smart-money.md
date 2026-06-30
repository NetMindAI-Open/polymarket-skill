# Smart-money / informed-flow strategy

**Goal:** Detect large, informed directional flow and follow it before price fully reflects it.
**Auto-execute:** no — always escalate (directional).

## Data to pull
- Shortlist FIRST from the shared universe using fields already on each row — rank candidates by elevated `volume_ratio` (plus `price_change_pct`, `liquidity`, token ids) and keep only the top movers. Never enrich every candidate one-call-at-a-time as you scan.
- Then enrich ONLY the shortlist in a single batched pass. Per candidate you need two tools:
  - `get_trades` `{"token_id":"…","limit":200}` — large prints, direction, counterparties if exposed.
  - `get_market_stats` `{"condition_id":"…","interval":"6h"}` — net buy/sell flow.
- Prefer native `mcp__polymarket__get_trades` / `mcp__polymarket__get_market_stats` when reachable (one persistent session, sub-second calls, no per-call handshake).
- Otherwise use ONE `assets/poly-mcp.sh --batch` pass: emit NDJSON on stdin, one object per line `{"id":"<token_or_condition>","tool":"get_trades|get_market_stats","args":{…}}`, read back `{"id":…,"ok":true,"result":{…}}`; a per-call failure returns `{"ok":false,"error":…}` without aborting the batch. The `id` joins each result to its market. NEVER loop single `poly-mcp.sh <tool>` calls — each pays a ~5s handshake.
- The fan-out is 2 calls × shortlist size; if the shortlist is large, shard across ~4 parallel `poly-mcp.sh --batch` invocations to also hide the ~2s/call server latency.
- `poly -o json data positions <address>` and `poly -o json data value <address>` — profile a wallet behind notable flow (any address is readable). These are poly-CLI calls, NOT MCP, so they stay as-is and are not part of the `--batch` NDJSON.

## Signal logic
- Concentrated large prints on one side (not retail-sized noise) with net flow confirming direction.
- Optional corroboration: the wallet driving it shows a sizeable / historically directional portfolio.
- Price hasn't yet fully moved to where the flow implies (room to follow).

## Disqualifiers
- Flow is small / evenly two-sided (no signal).
- Price already gapped to the implied level (no edge left).
- Single wallet with no track record and no corroborating flow (could be noise or manipulation).

## Confidence rubric
- 0.8+: large one-sided prints + confirming net flow + (optional) credible wallet, with room left.
- 0.6–0.8: decent flow signal, limited corroboration.
- < 0.6: drop.

## Output mapping
- `proposed_action`: BUY the side the informed flow favors, `order_type` "limit" near best price; `size_usd` ≤ cap.
- `signal`: `{ "large_print_count", "net_flow", "wallet_address", "wallet_value_usd", "implied_vs_current_gap" }`.
