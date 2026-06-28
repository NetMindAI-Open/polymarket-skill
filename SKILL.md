---
name: polymarket
description: Query and trade on Polymarket prediction markets — search markets, check live odds/order books, view positions and balances, place and cancel orders, and run a multi-agent opportunity scan that hunts mispricings and arbitrage across strategies. Use when the user mentions Polymarket, prediction-market odds, betting on an event/election/crypto outcome, wants to check or trade a market's probability, or asks to scan/find Polymarket opportunities.
---

# Polymarket

Drive the `poly` CLI to query and trade on Polymarket prediction markets. This skill is the operating
manual; `poly` does the work. Reads are public and free; trades spend real USDC on Polygon.

## Prerequisite

`poly` must be installed and on `PATH`, and (for anything beyond public market reads) a signer key must
be configured. If `poly` is missing or `poly wallet show` reports no key, see [README.md](README.md)
for install and key setup. Verify quickly:

```bash
poly -o json markets search "test" --limit 1   # works with no key (public)
poly -o json wallet show                        # errors if no key configured
```

## Golden rules

1. **Always pass `-o json`** — put it *before* the subcommand: `poly -o json <command> …`. Table mode is
   for humans; JSON is parseable and includes fields (token ids, condition ids) that table mode omits.
2. **Judge success by the exit code, not the text** — `0` = success, `1` = failure (order rejected,
   validation error, declined). On failure, JSON output carries `{"error": "<message>"}`.
3. **Never print, echo, or log the private key.** The CLI never prints it; don't ask the user to paste it
   into chat — point them at `poly setup` (hidden prompt) or the `POLYMARKET_PRIVATE_KEY` env var.

## Command map

Full catalog with every flag and JSON shape: [reference/commands.md](reference/commands.md).

**Read freely** (safe to call any time; most need only a configured key, market reads need nothing):

| Command | Purpose |
|---|---|
| `markets search <q>` · `markets get <ref>` · `markets list` | Find markets / odds (public, no key) |
| `data positions [addr]` · `data value [addr]` | On-chain positions & portfolio value |
| `clob orders` · `clob order <id>` · `clob trades` | Your open orders / one order / trade history |
| `clob balance --asset-type collateral` | USDC cash (or `conditional --token <id>` for shares) |
| `wallet show` · `wallet address` | Your signer EOA & deposit wallet (never the key) |

**Spend / write** (move money or change state — see safety below):

| Command | Purpose |
|---|---|
| `buy` · `sell` | Friendly limit (default) or `--market` order |
| `clob create-order` · `clob market-order` · `clob post-orders` | Explicit limit / market / batch |
| `clob cancel <id>` · `clob cancel-orders <ids>` · `clob cancel-market` · `clob cancel-all` | Cancel orders |
| `wallet create` · `wallet import` · `wallet reset` · `setup` | Key management |

## Trading workflow

Once a key is configured this skill operates **autonomously** — it may submit live orders with `--yes`
without asking for per-order human approval. Recommended flow for each trade:

1. **Resolve the market.** `markets search` / `markets get` → get the **market** slug or the CLOB
   `token_id` for the outcome you want. (Note: an *event* slug like `fifwc-tur-usa-2026-06-25` is not a
   *market* slug — drill down to the specific market, e.g. `…-usa`.)
2. **Dry-run sanity check (recommended).** Run the same order with `--dry-run`; it builds, signs, and
   prints the order locally without submitting. Parse the preview (price, size, ~notional, wallet) and
   confirm it matches intent.
3. **Submit.** Re-run with `--yes` (no `--dry-run`). Parse `{"result": "ACCEPTED order_id=… status=…"}`
   or `{"result": "REJECTED code=… message=…"}`, and the exit code.
4. **Handle approvals.** If a submit fails with `InsufficientAllowanceError`, the wallet isn't approved
   for trading — see *Wallet setup* below; do not retry blindly.

Market-order side semantics: a market **BUY** spends `--usd`; a market **SELL** delivers `--size`.
Mixing them is rejected up front.

## Wallet setup & first-time activation — read this before a new wallet's first trade

**`poly wallet import` / `poly wallet create` only configures the *signing key*. It does NOT make a
brand-new wallet ready to trade.** A wallet that has never been used on Polymarket can sign orders and
pass `--dry-run`, but its live orders will fail until it is activated on Polymarket's side.

**When the user imports/creates a key, or mentions a new or never-used wallet, proactively tell them**
(before attempting any live `buy`/`sell`):

> If this wallet is brand-new (never used on Polymarket), do this on the **website** first:
> 1. Go to **polymarket.com** and connect/log in with this wallet (e.g. import the private key into a
>    browser wallet like MetaMask, then click **Connect** on the site — or use the email/Magic login that
>    owns it).
> 2. **Deposit USDC** into the account. Funds live on the **deposit wallet**, not your signer address.
> 3. Complete the on-screen **"Enable Trading" approvals**. This deploys your proxy/deposit wallet and
>    grants the USDC + conditional-token (CTF) allowances the exchange needs. These on-chain approvals
>    are easiest done on the website (gasless); doing them via CLI requires gas/relayer setup.

Until that's done, live orders fail with `InsufficientAllowanceError` or insufficient-balance — and a
clean `--dry-run` is **not** proof of readiness (it only checks signing).

**Read-only readiness checks** (run these before a new wallet's first live trade):

- `poly -o json wallet show` → confirm the **deposit wallet** address matches polymarket.com/settings.
  (Signer EOA ≠ deposit wallet; the deposit wallet holds funds and approvals.)
- `poly -o json clob balance --asset-type collateral` → is USDC actually funded?

## Trading safety (guidance, not enforced)

This skill does **not** enforce spending limits — that was a deliberate design choice. Treat the
following as obligations on the agent's behavior:

- Prefer a `--dry-run` pass before any live order and confirm the preview.
- Honor any per-order or per-day spending limit the user states; if they haven't set one and an order is
  large, surface the notional and confirm before submitting.
- A wallet must be funded **and** approved (see above) before live orders can fill.

## Recipes

Copy-pasteable multi-step workflows (find→price→preview→submit, check positions, cancel a market's
orders, activate a new wallet): [reference/recipes.md](reference/recipes.md).

## Opportunity scanning (multi-agent)

When the user asks to **scan / find opportunities** (mispricings, arbitrage, movers worth
trading), run the orchestration playbook in [reference/orchestration.md](reference/orchestration.md).
In one on-demand pass it: scouts a shared candidate universe via the MCP, fans out six
parallel strategy sub-agents (momentum, mean-reversion, multi-outcome-arb, spread-capture,
risk-free-arb, smart-money — see [reference/strategies/](reference/strategies/)), synthesizes
and ranks their Opportunity objects, then runs each through the deterministic risk gate
(`assets/risk_gate.py`).

**Semi-auto execution.** The risk gate decides per opportunity: **auto-execute** (only the
structural arbs — `risk-free-arb`, `multi-outcome-arb` — when confident and within limits),
**escalate** (everything else, incl. all directional strategies → ask the user), or **skip**.
Auto-executed orders always run `--dry-run` and a preview match before `--yes`. Hard limits
live in `~/.config/polymarket/agent.json` (see [reference/config.example.json](reference/config.example.json));
conservative defaults apply if absent, and the user may override limits inline for a run.

**MCP access.** Reach the polymarket MCP through [assets/poly-mcp.sh](assets/poly-mcp.sh)
(see [reference/mcp.md](reference/mcp.md)); native `mcp__polymarket__*` calls may be blocked
by a health-check hook false positive.
