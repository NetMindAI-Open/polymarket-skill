# Smart-money / informed-flow strategy

**Goal:** Detect large, informed directional flow and follow it before price fully reflects it.
**Auto-execute:** no — always escalate (directional).

## Data to pull
- From the shared universe: markets with elevated `volume_ratio`.
- `assets/poly-mcp.sh get_trades '{"token_id":"…","limit":200}'` — large prints, direction, counterparties if exposed.
- `assets/poly-mcp.sh get_market_stats '{"condition_id":"…","interval":"6h"}'` — net buy/sell flow.
- `poly -o json data positions <address>` and `poly -o json data value <address>` — profile a wallet behind notable flow (any address is readable).

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
