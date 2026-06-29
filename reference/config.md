# Scanner configuration (`agent.json`)

The opportunity scanner's risk gate reads its hard limits from a JSON config file. Tuning these
controls how much the agent may trade and when it auto-executes vs. asks you.

## Where it lives

```
~/.config/polymarket/agent.json
```

The file is **optional**. If it's absent, the gate uses the conservative defaults baked into
`assets/risk_gate.py` (shown below). If present, your values override the defaults; you only need to
include the keys you want to change — omitted keys keep their default.

## Set it up

```bash
mkdir -p ~/.config/polymarket
cp reference/config.example.json ~/.config/polymarket/agent.json
# then edit the values
```

To go back to the conservative defaults at any time, just delete the file:

```bash
rm ~/.config/polymarket/agent.json
```

You can also override limits **inline for a single run** — e.g. tell the agent "scan, but only $30
total today" — without editing the file.

## Keys

| Key | Default | Meaning | Effect of changing it |
|---|---|---|---|
| `max_notional_per_order_usd` | `10` | Max USD a single auto-executed order may spend. | ↑ bigger individual bets; ↓ smaller. Must be > 0. |
| `max_total_per_run_usd` | `50` | Max cumulative USD auto-executed across one scan run (the per-run ceiling). | ↑ more total capital deployed per scan; ↓ less. |
| `min_confidence_auto` | `0.75` | Min strategy confidence (0–1) for an auto-eligible opportunity to **auto-execute**; below this it **escalates** to you instead. | ↓ auto-fires on weaker signals (more aggressive); ↑ only the most confident. |
| `min_confidence_report` | `0.5` | Below this confidence an opportunity is **dropped as noise** (not even reported). | ↓ surfaces weaker ideas; ↑ only stronger ones reach you. |
| `min_liquidity_usd` | `5000` | Market-level liquidity floor; thinner markets are **skipped**. | ↓ allows trading thinner markets (riskier fills/exits); ↑ stricter. |
| `min_depth_multiple` | `2` | Required order-book depth **at the order price**, as a multiple of the order size (2 = need ≥ 2× your size resting). | ↓ accepts thinner books; ↑ demands deeper books. |
| `max_book_take_pct` | `25` | Max % of the resting depth at price that a single order may consume (caps your market impact). | ↑ allows orders that move the book more; ↓ gentler. |
| `auto_execute_strategies` | `["risk-free-arb", "multi-outcome-arb"]` | Allowlist of strategies that may **auto-execute** within limits. Every other strategy **escalates** for human confirmation regardless of confidence. | Add strategies to let them auto-fire (see safety note). |

The six strategy names are: `momentum`, `mean-reversion`, `multi-outcome-arb`, `spread-capture`,
`risk-free-arb`, `smart-money`.

## How the gate uses these

For each opportunity the gate (`assets/risk_gate.py`) returns one of three decisions, in this order:

- **skip** — confidence below `min_confidence_report`, OR market liquidity below `min_liquidity_usd`,
  OR depth below `min_depth_multiple × size`, OR order over `max_notional_per_order_usd`, OR the run
  total would exceed `max_total_per_run_usd`, OR the order would take more than `max_book_take_pct` of
  resting depth.
- **auto-execute** — the strategy is in `auto_execute_strategies` **and** confidence ≥
  `min_confidence_auto` **and** all the caps above are satisfied. The order still runs `--dry-run` and
  a preview match before `--yes`.
- **escalate** — everything else (all directional strategies, and any allowlisted arb that misses an
  auto condition) → presented to you for confirmation.

## Safety notes

- **Real money.** Auto-execution spends real USDC on Polygon. These limits are the enforcement layer —
  the gate is deterministic code, not a suggestion to the LLM.
- **Adding directional strategies to `auto_execute_strategies` removes the human-in-the-loop** for
  judgment trades: `momentum`, `mean-reversion`, `spread-capture`, and `smart-money` would then place
  real orders **without asking you**. The default keeps only the two deterministic structural-arb
  strategies on auto.
- **`spread-capture` needs order management v1 doesn't have** (cancel/timeout of resting limit orders).
  Auto-firing it can leave dangling orders — keep it on escalate unless you're managing orders yourself.
- **Wallet readiness still applies.** Even an auto-execute decision will fail with
  `InsufficientAllowanceError` unless the deposit wallet is funded and trading-approved (see
  [recipes.md](recipes.md) "Activate a brand-new wallet").

## Example

A moderately aggressive config that still keeps directional trades on escalate:

```json
{
  "max_notional_per_order_usd": 25,
  "max_total_per_run_usd": 150,
  "min_confidence_auto": 0.70,
  "min_confidence_report": 0.5,
  "min_liquidity_usd": 3000,
  "min_depth_multiple": 1.5,
  "max_book_take_pct": 35,
  "auto_execute_strategies": ["risk-free-arb", "multi-outcome-arb"]
}
```

The committed defaults live in [config.example.json](config.example.json).
