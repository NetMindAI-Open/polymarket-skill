# Spread-capture / liquidity-provision strategy

**Goal:** On wide-spread but liquid markets, post passive limit orders inside the spread to capture it.
**Auto-execute:** no — always escalate (directional/inventory risk).

## Data to pull
- From the shared universe: candidates surfaced by `screen_markets sort_by="spread"` with adequate `liquidity`.
- `assets/poly-mcp.sh get_order_book '{"token_id":"…"}'` — best bid/ask and resting sizes.
- `assets/poly-mcp.sh get_market_stats '{"condition_id":"…","interval":"24h"}'` — two-sided activity (will the post get filled?).

## Signal logic
- `spread` materially wide (e.g. ≥ 3¢) with `market_liquidity_usd` above floor and steady two-sided trade_count.
- Room to post inside the spread and still leave edge after the expected adverse-selection cost.
- Not trending hard (a wide spread on a fast mover is adverse selection, not capture).

## Disqualifiers
- Thin or one-sided flow (post won't fill, or fills only when wrong).
- Near resolution / strong momentum (adverse selection dominates).
- Spread already tight relative to tick size.

## Confidence rubric
- 0.8+: wide stable spread, balanced two-sided flow, no trend.
- 0.6–0.8: workable but thinner or slightly trending.
- < 0.6: drop.

## Output mapping
- `proposed_action`: `order_type` "limit" posted inside the spread (BUY just above best bid or SELL just below best ask); `size_usd` ≤ cap.
- `signal`: `{ "spread", "best_bid", "best_ask", "two_sided_trade_count" }`.
- Note in `risks`: requires later cancel/timeout management (out of scope for v1 auto-fire — escalate).
