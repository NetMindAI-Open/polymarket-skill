# Polymarket Multi-Agent Opportunity Scanner — Design

**Date:** 2026-06-28
**Status:** Approved design (pre-implementation)
**Project:** polymarket-skill

## Summary

Extend the existing instruction-only `polymarket` skill so a single on-demand request
("scan Polymarket for opportunities") drives a **scout pass** plus **six parallel strategy
sub-agents** over the two existing tool surfaces (polymarket MCP for read/analytics, `poly`
CLI for trade/account). Sub-agents return uniform `Opportunity` objects; the orchestrator
deduplicates, ranks, and runs each through a **risk gate** that either auto-executes a real
order within hard limits, escalates it for human confirmation, or skips it.

The skill stays instruction-only except for one **thin transport helper** (`assets/poly-mcp.sh`)
that performs the MCP-over-HTTP handshake. No strategy logic lives in code — strategies are
specs the sub-agents follow.

## Goals

- Turn the two tool surfaces into an orchestrated opportunity hunt across six strategy lenses.
- Keep the skill thin: instructions + specs + config + one transport helper.
- Semi-autonomous execution: deterministic structural arbs may auto-fire within hard limits;
  judgment-heavy directional trades escalate for human confirmation.
- Safe by default: conservative limits, dry-run-before-live, depth/liquidity checks.

## Non-Goals (v1 — explicitly deferred)

- Scheduling / recurring loops (use `/schedule` or `/loop` later).
- Cross-run state, dedup memory, or new-opportunity notifications.
- Backtesting, PnL attribution, strategy performance tracking.
- Auto-firing directional strategies (momentum, mean-reversion, spread-capture, smart-money).

## Decisions (locked during brainstorming)

| Decision | Choice |
|---|---|
| System boundary | **Semi-auto execution** — real orders within hard limits; escalate over-limit / low-confidence |
| Strategy set | 6 archetypes (below) |
| Orchestration | **Pure instruction** — SKILL.md drives sub-agents; no new runtime |
| Data flow | **Scout-then-specialists** — one shared scan → fan out to specialists |
| Limit config | **Config file + conservative defaults + inline override** |
| Run cadence | **On-demand one-shot** (v1) |
| MCP transport | **Thin helper** `assets/poly-mcp.sh` (curl handshake) |
| Auto-execute allowlist | **Only structural arbs** (`risk-free-arb`, `multi-outcome-arb`); 4 directional strategies escalate |

## Architecture — orchestration flow

```
[0] Preflight  → load config; verify poly key (wallet show) + MCP reachability (poly-mcp.sh init)
[1] Scout      → ONE shared scan: screen_markets ×4 (price_change / volume_spike / spread /
                 liquidity) + list_events → candidate universe (≈50–150 markets with stats)
[2] Fan-out    → dispatch 6 strategy sub-agents IN PARALLEL, each receives
                 { universe, its strategy spec, tool access, config limits }
[3] Collect    → each sub-agent returns Opportunity[]
[4] Synthesize → orchestrator dedups (by condition_id+outcome) + scores + ranks → ledger
[5] Risk gate  → per opportunity: auto-execute | escalate | skip
[6] Execute    → poly --dry-run preview → verify preview matches → poly --yes (within limits only)
[7] Report     → ranked table + theses + execution outcomes + escalations awaiting confirmation
```

The orchestrator is the main agent following `reference/orchestration.md`. Sub-agents are
dispatched with the Agent tool; each runs read-only discovery/enrichment and returns data
(no sub-agent places orders — execution is centralized in the orchestrator so the risk gate
and per-run total are enforced in one place).

## Components

All artifacts are instructions/specs/config except the one transport helper.

| Artifact | Role |
|---|---|
| `SKILL.md` (new section) | "Opportunity scanning (multi-agent)" section + triggers ("find/scan opportunities") |
| `reference/orchestration.md` | Scout spec, fan-out protocol, synthesis/dedup/scoring, risk gate, output format |
| `reference/strategies/momentum.md` | News/repricing continuation |
| `reference/strategies/mean-reversion.md` | Overreaction fade on thin-info spikes |
| `reference/strategies/multi-outcome-arb.md` | Mutually-exclusive outcomes summing ≠ 100% |
| `reference/strategies/spread-capture.md` | Wide spread + liquidity → passive limit orders |
| `reference/strategies/risk-free-arb.md` | YES+NO < 1, cross-market logical arb, negRisk redemption |
| `reference/strategies/smart-money.md` | Follow informed directional flow (trades, market_stats, address positions) |
| `reference/mcp.md` | How to call the MCP + health-check hook fix |
| `assets/poly-mcp.sh` | Thin MCP-over-HTTP transport helper (handshake → session → tools/call). **No strategy logic.** |
| `~/.config/polymarket/agent.json` | Limits + scan params; conservative defaults if absent |

## Data contracts

### Candidate universe item (scout output)

From `screen_markets`: `condition_id`, `slug`, `question`, `event_id`, `token_id_yes`,
`token_id_no`, `yes_price`, `volume_24h`, `liquidity`, `spread`, `best_bid`, `best_ask`,
`trade_count`, `price_change_pct`, `volume_ratio`, `open_price`, `close_price`.

### Opportunity object (every strategy sub-agent returns)

Uniform schema so the orchestrator can rank and the gate can decide:

```jsonc
{
  "strategy": "momentum",
  "condition_id": "0x…",
  "slug": "…",
  "token_id": "…",
  "outcome": "yes",                  // yes | no
  "thesis": "<one paragraph: why this is an edge>",
  "signal": { /* strategy-specific metrics, e.g. volume_ratio, sum_of_outcomes */ },
  "proposed_action": {
    "side": "BUY",                   // BUY | SELL
    "order_type": "limit",           // limit | market
    "price": 0.62,                   // required for limit
    "size_usd": 8
  },
  "edge_estimate": "<mispricing in cents / bps>",
  "confidence": 0.0,                 // 0.0–1.0, per the strategy's confidence rubric
  "liquidity_check": { "depth_usd_at_price": 0, "est_slippage": 0 },
  "risks": ["…"]
}
```

Each strategy spec defines: goal · which MCP/CLI data to pull · the signal logic · disqualifiers ·
the `signal` fields it populates · a confidence rubric.

## Risk gate (semi-auto core)

### Config (`~/.config/polymarket/agent.json`) with conservative defaults

| Key | Default | Meaning |
|---|---|---|
| `max_notional_per_order_usd` | 10 | Per-order cap |
| `max_total_per_run_usd` | 50 | Cumulative cap across one scan run |
| `min_confidence_auto` | 0.75 | Below → escalate (still reported) |
| `min_confidence_report` | 0.5 | Below → dropped as noise (not reported) |
| `min_liquidity_usd` | 5000 | Market-level liquidity floor |
| `min_depth_usd_at_price` | 2× order size | Book depth at the order price |
| `max_book_take_pct` | 25 | Max % of resting depth a single order may take |
| `auto_execute_strategies` | `["risk-free-arb", "multi-outcome-arb"]` | Allowlist for auto-fire |

Inline overrides (natural language, e.g. "only $30 total today") take precedence for that run.

### Decision per opportunity

- **skip** — confidence < `min_confidence_report` (dropped as noise), OR liquidity/depth fails,
  OR notional > `max_notional_per_order_usd`, OR running total would breach `max_total_per_run_usd`,
  OR order would take > `max_book_take_pct` of depth. (Opportunities with
  `min_confidence_report ≤ confidence < min_confidence_auto` are reported and escalated, not skipped.)
- **auto-execute** — `strategy ∈ auto_execute_strategies` AND `confidence ≥ min_confidence_auto`
  AND within all caps → `poly -o json … --dry-run` → assert preview (token, side, price, ~notional,
  wallet) matches `proposed_action` → re-run with `--yes`. Add filled notional to the run total.
- **escalate** — everything else (all directional strategies; any structural arb that fails an
  auto condition) → present the proposed order to the user and wait for explicit confirmation.

Execution is centralized in the orchestrator (not the sub-agents) so the per-run total and the
gate are enforced in exactly one place.

## Output (v1: chat)

1. **Ranked table:** `rank · strategy · market · action · edge · confidence · liquidity · gate decision`.
2. **Executed orders:** for each auto-executed opportunity, `order_id` + status from the
   `{"result": "ACCEPTED order_id=… status=…"}` payload.
3. **Escalations:** proposed orders awaiting the user's go, each with thesis + preview.

No persisted run file in v1.

## MCP prerequisite (must address first)

Native `mcp__polymarket__*` tools are blocked by the ECC plugin's `mcp-health-check.js`
**false-positive**: the hook probes the endpoint with `Accept: application/json` only, the server
correctly rejects with HTTP 406 ("must accept both application/json and text/event-stream"), and
the hook declares the (healthy) server unavailable and blocks all calls. Verified: with the
correct `Accept` header the server returns 200 (`serverInfo: polymarket-data v1.28.1`).

Two-part handling:
1. **Transport (required):** `assets/poly-mcp.sh` performs the full handshake (initialize →
   capture `Mcp-Session-Id` → `notifications/initialized` → `tools/call`) with correct headers,
   reading the bearer token from the configured MCP entry. Sub-agents and the scout call MCP
   through this helper, so the system works regardless of the hook.
2. **Native fix (optional, documented):** whitelist `polymarket` in the health-check, or fix its
   `Accept` header, so interactive native `mcp__polymarket__*` calls also work. Documented in
   `reference/mcp.md`; not required for the scanner to function.

## Testing

- **Scout:** `poly-mcp.sh` returns parseable JSON; scout assembles a well-formed universe.
- **Strategy specs:** run each against a captured universe fixture → assert valid `Opportunity`
  objects (schema + required fields).
- **Risk gate (the money-guarding piece — real test):** feed synthetic opportunities + a config
  to the gate logic, assert auto / escalate / skip decisions across boundary cases (at cap, over
  cap, just-below confidence, depth fail, non-allowlisted strategy).
- **Execution safety:** assert every auto-execute path runs `--dry-run` and a preview match
  before `--yes`.

## Risks & mitigations

- **Scout blind spot** (a market no screener surfaced) → arb and smart-money agents get a small
  targeted-pull allowance beyond the shared universe.
- **Stale snapshot between scout and execution** → re-check order book / best price at execution
  time in the dry-run preview; reject if it moved beyond tolerance.
- **MCP token handling** → helper reads the token from config; never echoes it to logs/chat.
- **Over-trading** → centralized per-run total cap + per-order cap + depth-take cap.
