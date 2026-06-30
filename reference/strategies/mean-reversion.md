# Mean-reversion / overreaction strategy

**Goal:** Fade sharp moves that lack informational backing — bet on reversion toward the prior level.
**Auto-execute:** no — always escalate (directional).

## Data to pull
- Shortlist FIRST from the shared universe using fields already on each row — candidates with large `price_change_pct` but modest `volume_ratio` (plus `spread`, `liquidity`, `best_bid/ask`, token ids, `condition_id`). Only enrich the shortlist.
- Then gather all three enrichment tools in ONE batched pass (3 calls per shortlisted candidate), joined by an `id` key — never loop single `poly-mcp.sh <tool>` calls as you scan:
  - `get_price_history {"token_id":"…","interval":"1h"}` — locate the pre-spike level.
  - `get_trades {"token_id":"…","limit":100}` — is the move a few large prints or broad?
  - `get_market_stats {"condition_id":"…","interval":"24h"}` — flow balance.
- Prefer the native `mcp__polymarket__*` tools (one persistent session, sub-second, no per-call handshake). Otherwise pipe NDJSON into ONE `poly-mcp.sh --batch` pass: one `{"id":"<cand>:<tool>","tool":"<tool>","args":{…}}` per line in, `{"id":…,"ok":true,"result":{…}}` per line out (a per-call `{"ok":false,"error":…}` does not abort the batch).
- This fan-out is 3× the shortlist; once it grows past ~10–15 candidates (~30–45 calls), shard across ~4 parallel `poly-mcp.sh --batch` invocations to hide the ~2s/call server latency — a measured 48-call run dropped from >120s (per-call, timed out) to ~30s. See reference/mcp.md "Speed: never loop single calls".

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
