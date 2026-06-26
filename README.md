# polymarket skill

An agent skill for querying and trading on [Polymarket](https://polymarket.com) prediction markets. It
teaches an AI agent to drive the [`poly`](../polymarket_cli) CLI safely and as structured workflows —
search markets, read odds and positions, and place or cancel orders.

It's **instruction-only**: no code of its own. `poly` is the single source of truth; this skill is the
operating manual ([SKILL.md](SKILL.md)) plus reference docs.

## What's inside

| File | Purpose |
|---|---|
| [SKILL.md](SKILL.md) | The skill: trigger description, golden rules, command map, trading + wallet workflow, safety. |
| [reference/commands.md](reference/commands.md) | Full `poly` command catalog: flags, JSON shapes, read/write tags. |
| [reference/recipes.md](reference/recipes.md) | Copy-pasteable workflows (find→price→preview→submit, account checks, new-wallet activation). |

## Prerequisites

This skill calls the `poly` CLI, which must be installed and on your `PATH`. `poly` is **not on PyPI**
yet, so install it from source:

```bash
# from a local checkout of the CLI repo:
uv tool install --from /path/to/polymarket_cli poly-cli
# or with pipx:
pipx install /path/to/polymarket_cli

# verify:
poly -o json markets search "test" --limit 1
```

Then configure a signer key (only needed for account reads and trading, not public market search):

```bash
poly setup                     # hidden prompt, writes ~/.config/polymarket/config.json
# or: poly wallet import 0x<key>
# or: export POLYMARKET_PRIVATE_KEY=0x...
```

> **New wallet?** Configuring a key does **not** make a brand-new wallet trade-ready. You must first
> activate it on polymarket.com (connect the wallet → deposit USDC → "Enable Trading" approvals). See
> the "Activate a brand-new wallet" recipe in [reference/recipes.md](reference/recipes.md).

## Install the skill

**Claude Code** — copy this folder into your skills directory so `SKILL.md` sits at its root:

```bash
cp -R polymarket-skill ~/.claude/skills/polymarket
```

Restart Claude Code; the skill activates when you mention Polymarket / prediction-market odds / placing
a bet.

**OpenClaw / clawhub** — the `SKILL.md` frontmatter (`name` + `description`) is the portable common
subset, so the same folder installs as an OpenClaw skill. To publish for others, the `poly` CLI it
depends on must be reachable by them (publish `poly-cli` to PyPI, or point the install step above at the
CLI's git repo).

## Safety

Trades spend **real USDC on Polygon**. This skill is configured for an **autonomous** posture (the agent
may submit live orders with `--yes`) and does **not** enforce spending limits — those are guidance in
[SKILL.md](SKILL.md), not hard caps. Prefer a `--dry-run` preview before live orders, and set explicit
per-order / per-day limits with the agent if you want them respected.
