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

> **Speed — read this once.** Reading is the slow part of a scan, and the cause is almost
> always a loop of single `poly-mcp.sh` calls: each pays the full ~5s MCP handshake. Use the
> native `mcp__polymarket__*` tools (persistent session, no handshake) when reachable, or
> `poly-mcp.sh --batch` (one handshake for many calls) otherwise — never a per-call loop. Batch
> Gamma metadata into one `condition_ids=a&condition_ids=b&…` request via serial `curl` (concurrent
> requests get 429-rate-limited). See [mcp.md](mcp.md#speed-never-loop-single-calls--go-native-or-batch).

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
Give each: the candidate universe, its strategy spec, the limits, and read-only enrichment
access. **In each sub-agent's prompt, spell out the fast read path** (don't assume it knows):
shortlist candidates from the universe fields first, then gather enrichment for the shortlist
in a *single batched pass* — native `mcp__polymarket__*` tools, or one `poly-mcp.sh --batch`
pass (sharded ~4-way for a large fan-out) — **never a per-call `poly-mcp.sh <tool>` loop**, which
re-pays the ~5s MCP handshake every call. The `poly` CLI stays available for non-MCP reads (e.g.
smart-money wallet profiling). The arb and smart-money agents may do small targeted extra pulls
beyond the universe (scout blind-spot coverage). See the Speed note above / [mcp.md](mcp.md).
Each returns an array of Opportunity objects matching `reference/opportunity.schema.json`.

**Bilingual prose (for the zh/en dashboard):** the dashboard defaults to Chinese with an EN toggle, so
instruct each sub-agent to write `thesis` and every `risks` entry **bilingually** as
`{"en": "…", "zh": "…"}` (the schema accepts a plain string *or* this object). Keep the technical
`signal` map and `edge_estimate` as-is. A plain-string thesis still works — it just shows the same
text in both languages.

## 3. Synthesize
- Validate each returned object: `echo '<opportunity-json>' | python3 assets/risk_gate.py validate` (drop invalid ones, note them).
- Dedupe by `(condition_id, outcome)`; if two strategies surface the same one, keep the
  higher `confidence` and record both strategy names.
- Rank by `confidence` (tie-break by `edge_estimate`).

## 4. Risk gate (call the deterministic core per opportunity)
Track a running `run_total_usd`, starting at 0. For each ranked opportunity:

    echo '<opportunity-json>' | python3 assets/risk_gate.py decide --run-total <run_total_usd>

The output is `{"decision":"auto"|"escalate"|"skip","reason":"…"}`:
- **skip** — don't trade it, but **keep it** (with its `gate.reason`) for the dashboard. The mapper
  surfaces skips in Recommendations as low-confidence **WATCH** items whose first signal is that reason,
  so the user sees the candidate and *why* it was set aside.
- **escalate** — add to the escalation list (present to the user; do not execute now).
- **auto** — execute (Step 5), then add the filled `size_usd` to `run_total_usd`.

**Safety invariant:** `decide` only ever returns `auto` for the structural-arb strategies (`risk-free-arb`, `multi-outcome-arb`) — the gate's allowlist enforces this in one place. Never auto-execute a directional opportunity (momentum, mean-reversion, spread-capture, smart-money); if one ever shows `auto`, treat it as `escalate`.

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

## 6. Report (short text summary — not the final answer)
Lead with a brief ranked table, then **always continue to Step 7** and emit the dashboard as the
primary deliverable. Do **not** stop here — a text table alone is an incomplete scan.
- **Ranked table:** rank · strategy · market · action · edge · confidence · liquidity · gate decision.
- **Executed:** each auto order's `order_id` + status from `{"result":"ACCEPTED order_id=… status=…"}`.
- **Escalations:** proposed orders awaiting the user's go, each with thesis + dry-run preview.
- **Watch (skipped):** gated-out candidates with their reason — surfaced as low-confidence items, not traded.

## 7. Emit dashboard artifact (mandatory — this is the deliverable)
**Every scan ends here.** Turn the run into the visual dashboard and emit it as an **Artifact**; the
Step 6 table is only a companion summary, never a substitute — don't stop at the table. Attach each gate
result to its opportunity (`"gate": {"decision": …, "order_id": …}`), then let the deterministic
mapper assemble + inject `DATA` — **don't hand-write the JSON**:

1. **Curate + enrich.** The Markets tab is simply the **50 most-traded markets in the last 24h**:
   `build_data.py` takes the top 50 `universe` rows by `volume_24h` (dead YES≈0 markets dropped, all of
   them if the pool is smaller). So pass a `universe` pool that includes the genuinely active markets —
   `screen_markets` has no raw-volume sort, so add a broad pull (e.g. `sort_by="liquidity"`, high `limit`)
   to the scout universe and let the mapper rank it. **Enrich the 50 shown markets** (don't enrich fewer
   than you show, or cards render without candles/depth). For *that subset only*, fetch enrichment:
   - real **event slug** → `url`, plus `category` / `end_date` / `description` / `volume_total` — all from
     **one batched Gamma `curl`**: `…/markets?condition_ids=<a>&condition_ids=<b>&…` returns the whole subset
     in a single request (`events[].slug` for the URL; a market/guessed slug 404s). Don't loop one cid per request,
     and don't fire them concurrently (429).
   - `candles` (`get_price_history`), `depth` (`get_order_book_depth`), `net_flow` (`get_market_stats`) — this is
     the slow hotspot (~3 calls × subset). **Use native `mcp__polymarket__*` tools, or one `poly-mcp.sh --batch`
     pass** over all three-per-market calls; a per-call `poly-mcp.sh` loop pays the ~5s handshake every time and
     is what makes enrichment crawl (see the Speed note above / [mcp.md](mcp.md)).
   Enriching only the shown 50 (not all 50–150) keeps the payload small.
2. **Assemble `run.json`** = `{lang, generated_at, wallet_label, universe, opportunities(+gate), enrichment, account}`.
   `lang` is the dashboard's default language (`"zh"` default, or `"en"`) → `meta.lang`; the user can still flip
   the in-dashboard `中/EN` toggle. Put **every** gated opportunity in `opportunities` — `auto`, `escalate`, **and
   `skip`** (each carrying its `gate.decision` + `gate.reason`); skips render as low-confidence WATCH items, so
   dropping them hides candidates.
   For `account`, check the wallet first with `poly -o json wallet show`: **set up → gather it** (`clob balance
   --asset-type collateral`, `data value`, `data positions`, `clob orders`, `clob trades`); **no key / errors →
   set `account: null`** so the Account tab renders wallet-setup steps (Markets/Recommendations still work).
   Full shape: [artifacts.md](artifacts.md).
3. **Build + inject:**

       python3 assets/build_data.py --inject assets/dashboard-template.html < run.json > dashboard.html

   Emit `dashboard.html` as the artifact. The mapper maps opportunities→recommendations (gate decision →
   `executed`/`pending`/`skipped` pill; a `skip` is forced to the **low** band with its reason as the first
   signal) and sums `meta.stats` from the full universe.
4. **Caveat** the user: the dashboard is a snapshot frozen at `generated_at`; regenerate to refresh.
