# Mean-reversion / overreaction strategy

**Goal:** Fade sharp moves that lack informational backing — bet on reversion toward the prior level.
**Auto-execute:** no — always escalate (directional).

## Data to pull
- From the shared universe: candidates with large `price_change_pct` but modest `volume_ratio`.
- `assets/poly-mcp.sh get_price_history '{"token_id":"…","interval":"1h"}'` — locate the pre-spike level.
- `assets/poly-mcp.sh get_trades '{"token_id":"…","limit":100}'` — is the move a few large prints or broad?
- `assets/poly-mcp.sh get_market_stats '{"condition_id":"…","interval":"24h"}'` — flow balance.

## Signal logic
- Sharp price move on **thin** volume (`volume_ratio` near or below 1) or driven by a handful of prints.
- No corroborating sustained flow; the move looks like an air-pocket, not repricing.
- A clear prior level to revert toward in the price history.

## Disqualifiers
- High `volume_ratio` with consistent flow (that is momentum, not overreaction).
- Markets near a resolution deadline where the move may be correct, late information.
- Illiquid markets where reversion can't be exited (`market_liquidity_usd` below floor).

## Confidence rubric
- 0.8+: big move, `volume_ratio < 1`, move traced to 1–3 prints, clean prior level.
- 0.6–0.8: thin-ish move, plausible reversion.
- < 0.6: ambiguous — drop.

## Output mapping
- `proposed_action`: trade **against** the move (BUY the side that dropped / SELL the side that spiked), `order_type` "limit" near the prior level; `size_usd` ≤ cap.
- `signal`: `{ "price_change_pct", "volume_ratio", "prior_level", "print_concentration" }`.
