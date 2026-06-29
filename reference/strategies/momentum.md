# Momentum / news-repricing strategy

**Goal:** Catch markets repricing hard on fresh information and ride the continuation
before the book fully adjusts.
**Auto-execute:** no — always escalate (directional).

## Data to pull
- From the shared universe: candidates with high `price_change_pct` and `volume_ratio`.
- `assets/poly-mcp.sh get_market_stats '{"condition_id":"…","interval":"24h"}'` — buy/sell flow.
- `assets/poly-mcp.sh get_price_history '{"token_id":"…","interval":"1h"}'` — confirm a sustained move, not a single spike.
- `assets/poly-mcp.sh get_order_book_depth '{"token_id":"…","notional":100}'` — depth/slippage for sizing.

## Signal logic
- Move is recent, large (`price_change_pct` well above the universe median), and backed by `volume_ratio > 3`.
- Net flow (`get_market_stats`) is directionally consistent with the move (buys lifting YES, etc.).
- Price action shows follow-through across the last several 1h candles, not a wick that reverted.

## Disqualifiers
- Penny markets (`open_price < 0.05`) where a 1¢ tick reads as a huge % — exclude.
- Move already at an extreme (`yes_price > 0.95` or `< 0.05`) with little room left.
- Flow contradicts the price move (likely a squeeze/illiquid print).

## Confidence rubric
- 0.8+: large move + `volume_ratio > 10` + consistent flow + multi-candle follow-through.
- 0.6–0.8: solid move and volume, mixed follow-through.
- < 0.6: thin or contradictory — drop.

## Output mapping
- `proposed_action`: BUY the side the move favors, `order_type` "limit" at/just inside best ask (BUY) or best bid (SELL); `size_usd` ≤ config per-order cap.
- `signal`: `{ "price_change_pct", "volume_ratio", "net_flow", "candles_following" }`.
