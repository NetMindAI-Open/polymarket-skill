# Opportunity-scan orchestration playbook

The main agent runs this on demand ("scan Polymarket for opportunities"). Sub-agents
only research and return data; **only the orchestrator places orders**, so the risk
gate and the per-run total are enforced in exactly one place.

## 0. Preflight
- `poly -o json wallet show` — confirm a signer key is configured (needed to trade).
- `assets/poly-mcp.sh search_markets '{"query":"test","limit":1}'` — confirm MCP reachability.
- Load limits: read the config once with the defaults baked into `assets/risk_gate.py`
  (`~/.config/polymarket/agent.json` if present). Apply any inline override the user gave
  for this run (e.g. "only $30 total today").

## 1. Scout (one shared scan)
Build a candidate universe with four screens (drop penny noise with min filters):

    assets/poly-mcp.sh screen_markets '{"sort_by":"price_change","interval":"24h","min_liquidity":5000,"min_volume_24h":50000,"min_trade_count":100,"limit":25}'
    assets/poly-mcp.sh screen_markets '{"sort_by":"volume_spike","interval":"24h","min_liquidity":20000,"min_volume_24h":100000,"min_trade_count":50,"limit":25}'
    assets/poly-mcp.sh screen_markets '{"sort_by":"spread","interval":"24h","min_liquidity":10000,"limit":25}'
    assets/poly-mcp.sh screen_markets '{"sort_by":"liquidity","interval":"24h","limit":25}'

Merge + dedupe by `condition_id` into one universe (≈50–150 markets), each carrying the
fields from the screener (`yes_price`, `volume_24h`, `liquidity`, `spread`, `best_bid/ask`,
`price_change_pct`, `volume_ratio`, `open_price`, `close_price`, `token_id_yes/no`, `event_id`).

## 2. Fan-out (six parallel sub-agents)
Dispatch six sub-agents **in parallel**, one per strategy in `reference/strategies/`.
Give each: the candidate universe, its strategy spec, the limits, and access to
`assets/poly-mcp.sh` + the `poly` CLI for read-only enrichment. The arb and smart-money
agents may do small targeted extra pulls beyond the universe (scout blind-spot coverage).
Each returns an array of Opportunity objects matching `reference/opportunity.schema.json`.

## 3. Synthesize
- Validate each returned object: `python3 assets/risk_gate.py validate` (drop invalid ones, note them).
- Dedupe by `(condition_id, outcome)`; if two strategies surface the same one, keep the
  higher `confidence` and record both strategy names.
- Rank by `confidence` (tie-break by `edge_estimate`).

## 4. Risk gate (call the deterministic core per opportunity)
Track a running `run_total_usd`, starting at 0. For each ranked opportunity:

    echo '<opportunity-json>' | python3 assets/risk_gate.py decide --run-total <run_total_usd>

The output is `{"decision":"auto"|"escalate"|"skip","reason":"…"}`:
- **skip** — record the reason; do nothing.
- **escalate** — add to the escalation list (present to the user; do not execute now).
- **auto** — execute (Step 5), then add the filled `size_usd` to `run_total_usd`.

## 5. Execute (auto only — dry-run first, always)
For each `auto` opportunity, build the matching `poly` order from `proposed_action`:

    # 1) preview — never submits
    poly -o json buy --token-id <token_id> --usd <size_usd> --price <price> --dry-run   # limit example
    # verify the dry-run preview: token_id, side, price, and ~notional match proposed_action
    # 2) submit only if the preview matches
    poly -o json buy --token-id <token_id> --usd <size_usd> --price <price> --yes

Use SELL / `--market` / `--size` forms per `reference/commands.md` when the action calls
for them (market BUY spends `--usd`, market SELL delivers `--size`). If the preview does
**not** match, abort that order and move it to escalations. Re-check best price in the
preview; if the market moved beyond the proposed price, abort (stale-snapshot guard).

## 6. Report
- **Ranked table:** rank · strategy · market · action · edge · confidence · liquidity · gate decision.
- **Executed:** each auto order's `order_id` + status from `{"result":"ACCEPTED order_id=… status=…"}`.
- **Escalations:** proposed orders awaiting the user's go, each with thesis + dry-run preview.
