# CLAUDE.md

Context for developing **this repo** — the `polymarket` agent skill.
(To *use* the skill, start at [SKILL.md](SKILL.md).)

## What this is

An **instruction-only** Claude/OpenClaw skill driving the `poly` CLI + a Polymarket MCP to
query, trade, and run a multi-agent opportunity scan. Strategy logic lives in Markdown specs,
**not code**. The only executable code is three thin helpers:
- `assets/risk_gate.py` — money-guarding decision core (config + Opportunity validation + `decide()` + CLI).
- `assets/poly-mcp.sh` — MCP-over-HTTP transport (handshake → `tools/call`).
- `assets/build_data.py` — orchestration→artifact bridge: maps the scan's universe + gated opportunities (+ account) into the dashboard `DATA` and injects `assets/dashboard-template.html` (pure/stdlib, `tests/test_build_data.py`).

## Commands

```bash
# Tests — no pyproject/venv; uv pulls deps inline:
uv run --with pytest --with jsonschema pytest tests/ -v

# Risk gate (reads an Opportunity JSON on stdin):
echo '<opportunity-json>' | python3 assets/risk_gate.py decide --run-total <usd>
echo '<opportunity-json>' | python3 assets/risk_gate.py validate

# Polymarket MCP (read-only market data):
assets/poly-mcp.sh screen_markets '{"sort_by":"volume_spike","interval":"24h","limit":10}'

# Build the dashboard artifact (maps a scan run -> DATA -> injects template):
python3 assets/build_data.py --inject assets/dashboard-template.html < run.json > dashboard.html
```

## Layout

- `SKILL.md` — skill entry + activation triggers.
- `reference/orchestration.md` — multi-agent scan playbook (scout → 6 strategy agents → gate → report).
- `reference/strategies/*.md` — the six strategy specs (the "logic", as prose).
- `reference/config.md` + `config.example.json` — risk-gate limits (`~/.config/polymarket/agent.json`).
- `reference/commands.md` / `recipes.md` / `mcp.md` — poly catalog, workflows, MCP guide.
- `assets/risk_gate.py` + `assets/poly-mcp.sh` + `assets/build_data.py` — the only code.
- `assets/dashboard-template.html` + `reference/artifacts.md` — the dashboard **artifact** (self-contained HTML + `DATA` schema). Orchestration Step 7 builds it via `build_data.py`.
- `docs/superpowers/specs|plans/` — design spec + implementation plan.

## Gotchas

- **Use `assets/poly-mcp.sh`, not native `mcp__polymarket__*`.** The ECC `mcp-health-check` hook
  sends an incomplete `Accept` header, gets a 406, and wrongly blocks the (healthy) MCP. The helper
  sends `Accept: application/json, text/event-stream`.
- **`risk_gate.decide()` is the only thing that authorizes real money.** Keep it stdlib-only
  (`jsonschema` is imported lazily, inside `validate_opportunity` only). Any change to its 8 ordered
  checks or comparison operators must update the boundary tests in `tests/test_risk_gate.py`.
- **Auto-execute is allowlisted to structural arbs** (`risk-free-arb`, `multi-outcome-arb`) in
  `risk_gate.DEFAULTS` — the single enforcement point. Directional strategies always escalate.
- **Conservative limit defaults live in `risk_gate.DEFAULTS`**; a user `agent.json` overrides them.
  Keep the code defaults conservative — they're the safety floor.
- **`build_data.py` never fetches.** The orchestration step hands it the universe, gated opportunities,
  enrichment, and (only when a wallet is set up) account — a null `account` makes the dashboard render
  wallet-setup steps. Keep it pure/stdlib so `tests/test_build_data.py` stays hermetic.
