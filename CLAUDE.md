# CLAUDE.md

Context for developing **this repo** — the `polymarket` agent skill.
(To *use* the skill, start at [SKILL.md](SKILL.md).)

## What this is

An **instruction-only** Claude/OpenClaw skill driving the `poly` CLI + a Polymarket MCP to
query, trade, and run a multi-agent opportunity scan. Strategy logic lives in Markdown specs,
**not code**. The only executable code is two thin helpers:
- `assets/risk_gate.py` — money-guarding decision core (config + Opportunity validation + `decide()` + CLI).
- `assets/poly-mcp.sh` — MCP-over-HTTP transport (handshake → `tools/call`).

## Commands

```bash
# Tests — no pyproject/venv; uv pulls deps inline:
uv run --with pytest --with jsonschema pytest tests/ -v

# Risk gate (reads an Opportunity JSON on stdin):
echo '<opportunity-json>' | python3 assets/risk_gate.py decide --run-total <usd>
echo '<opportunity-json>' | python3 assets/risk_gate.py validate

# Polymarket MCP (read-only market data):
assets/poly-mcp.sh screen_markets '{"sort_by":"volume_spike","interval":"24h","limit":10}'
```

## Layout

- `SKILL.md` — skill entry + activation triggers.
- `reference/orchestration.md` — multi-agent scan playbook (scout → 6 strategy agents → gate → report).
- `reference/strategies/*.md` — the six strategy specs (the "logic", as prose).
- `reference/config.md` + `config.example.json` — risk-gate limits (`~/.config/polymarket/agent.json`).
- `reference/commands.md` / `recipes.md` / `mcp.md` — poly catalog, workflows, MCP guide.
- `assets/risk_gate.py` + `assets/poly-mcp.sh` — the only code.
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
