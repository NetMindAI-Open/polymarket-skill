# Spread-capture / liquidity-provision strategy

**Goal:** On wide-spread but liquid markets, post passive limit orders inside the spread to capture it.
**Auto-execute:** no — always escalate (directional/inventory risk).

## Data to pull
- Shortlist FIRST from the shared universe: keep candidates surfaced by `screen_markets sort_by="spread"` whose row already shows a materially wide `spread` and `liquidity`/`market_liquidity_usd` above floor — using only fields present on each row (spread, liquidity, best_bid/ask, token_id_yes, condition_id). Never enrich while you scan.
- THEN enrich ONLY the shortlist in one batched pass — never loop single `poly-mcp.sh <tool>` calls (each pays a ~5s handshake). Per shortlisted market gather two calls: `get_order_book {"token_id":"…"}` (best bid/ask + resting sizes) and `get_market_stats {"condition_id":"…","interval":"24h"}` (two-sided activity — will the post get filled?).
- Prefer the native `mcp__polymarket__get_order_book` / `mcp__polymarket__get_market_stats` tools when reachable (one persistent session, sub-second, no per-call handshake).
- Otherwise issue ONE `poly-mcp.sh --batch` pass: NDJSON on stdin, one object per line `{"id":"<token_or_condition>","tool":"get_order_book|get_market_stats","args":{…}}`; read NDJSON on stdout `{"id":…,"ok":true,"result":{…}}` and join by `id` back to each market (a per-call `{"ok":false,"error":…}` does not abort the batch).
- Fan-out is ~2 calls × shortlist size; once that exceeds ~20–30 calls, shard across ~4 parallel `poly-mcp.sh --batch` invocations to also hide the ~2s/call server latency (real run: 48 calls dropped from >120s to ~30s — see reference/mcp.md "Speed: never loop single calls").

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
