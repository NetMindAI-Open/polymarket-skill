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
4. **Handle approvals / flow errors.** Two distinct failures, two fixes:
   - `maker address not allowed, use the deposit wallet flow` → the client is on the EOA flow; live
     trading needs the **deposit-wallet (gasless) flow**, which requires a Relayer API key
     (`POLYMARKET_RELAYER_API_KEY`, a UUID from polymarket.com → Settings → API Keys). Configure it, retry.
   - `InsufficientAllowanceError` → the wallet isn't approved for trading. With the relayer flow set, run
     **`poly approve`** once (gasless: sets the deposit-wallet approvals for the standard + neg-risk
     exchanges), then retry. Otherwise see *Wallet setup* below. Do not retry blindly.

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
> 2. **Deposit USDC** into the account **from the website's own "Deposit" screen** — send only to the
>    address that screen shows. Funds live on the **deposit wallet**, not your signer address, and **not**
>    necessarily the address the CLI prints (see *Deposit-address safety* below).
> 3. Complete the on-screen **"Enable Trading" approvals**. This deploys your proxy/deposit wallet and
>    grants the USDC + conditional-token (CTF) allowances the exchange needs. Easiest on the website
>    (gasless). **CLI alternative:** with the relayer flow configured (`POLYMARKET_RELAYER_API_KEY`), run
>    **`poly approve`** to set these approvals gaslessly — no browser, no gas.

Until that's done, live orders fail with `InsufficientAllowanceError` or insufficient-balance — and a
clean `--dry-run` is **not** proof of readiness (it only checks signing).

**Read-only readiness checks** (run these before a new wallet's first live trade):

- `poly -o json wallet show` → **confirm the `api_wallet` it prints exactly equals the deposit-wallet
  address shown on polymarket.com/settings.** If they differ, do **not** trade or deposit — see the
  deposit-address warning below. (Signer EOA ≠ deposit wallet; the deposit wallet holds funds and approvals.)
- `poly -o json clob balance --asset-type collateral` → is USDC actually funded? A `0` balance on an
  account you believe is funded is a red flag that the CLI is pointed at the wrong wallet (see below).

### ⚠️ Deposit-address safety — the CLI's `api_wallet` can be the WRONG address

**Never treat any address the CLI prints as a deposit target, and never assume `api_wallet` is your real
account.** One private key deterministically derives **several distinct on-chain addresses** (the signer
EOA plus up to four contract wallets: POLY_PROXY, GNOSIS_SAFE, and *two* variants of the type-3 deposit
wallet). By default the CLI/SDK computes the deposit wallet from the *current* factory, which is **not
guaranteed to be the wallet your account actually deployed and funded.** We have observed a live account
where `poly wallet show` reported one deposit wallet (0 USDC) while the funds and the account
polymarket.com/CLOB actually recognize lived at a *different* derived address. Sending USDC to the
CLI-shown address in that case would strand the funds.

Therefore:

1. **Deposit only via the polymarket.com "Deposit" screen** — send USDC to the address that screen shows,
   never to an address the CLI/SDK printed. (This matches the "deposit via the website" note the CLI itself
   prints.)
2. **Verify before trusting the CLI account:** `poly wallet show`'s `api_wallet` **must** match the
   deposit-wallet address on polymarket.com/settings. If it doesn't, the SDK picked the wrong wallet.
3. **Fix a mismatch by pinning the wallet:** set `"wallet_address": "0x<the address polymarket.com shows>"`
   in `~/.config/polymarket/config.json`. The SDK will then sign/trade as that exact account instead of its
   default guess. (There is **no** `--wallet` CLI flag — `config.json` is the only override.)
4. **Consistency gate before any live order:** the wallet in the trade preview (`wallet`/`maker`) must be
   the funded account CLOB recognizes. If the SDK signs as address A but your balance lives on address B,
   orders are rejected for insufficient balance — stop and fix (step 3), don't retry.

The CLI also carries this warning **in its output** — a `note` field on `wallet show`, `wallet address`,
and `clob balance` — so you see it at call time. Read that `note`; don't ignore it.

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
live in `~/.config/polymarket/agent.json` (every key explained in [reference/config.md](reference/config.md));
conservative defaults apply if absent, and the user may override limits inline for a run.

**The dashboard is the deliverable — always emit it.** A scan is **not complete** until you render
the visual dashboard artifact (orchestration **Step 7** → [reference/artifacts.md](reference/artifacts.md)).
Build it **every run, by default**, without waiting to be asked; the ranked text table from Step 6 is only
a short summary that accompanies it, never a substitute. The only time you skip the artifact is when the
user explicitly says they want text only.

**MCP access.** Reach the polymarket MCP through [assets/poly-mcp.sh](assets/poly-mcp.sh)
(see [reference/mcp.md](reference/mcp.md)); native `mcp__polymarket__*` calls may be blocked
by a health-check hook false positive.

## Dashboard artifact (visualize)

**Default to the dashboard — build it proactively, don't wait for a second ask.** Render the multi-tab
HTML dashboard as an **Artifact** (instead of printing JSON/text tables) whenever you produce any of:
a **scan result** (always — see *Opportunity scanning* above), **more than a couple of markets**, or a
**positions/balance/portfolio** view — and of course whenever the user says show / visualize / "make a
dashboard" / "display my positions or markets". When in doubt, build it. The artifact is sandboxed — it
**cannot** run `poly` or call the MCP — so you inject a data snapshot at generation time. Full procedure,
`DATA` schema, and source map: [reference/artifacts.md](reference/artifacts.md).

**The dashboard is bilingual (中文/English), defaulting to Chinese** with an instant header `中/EN` toggle.
The UI translates itself; for a scan, have the strategy sub-agents write `thesis` and `risks` bilingually
(`{"en":…,"zh":…}`) so the per-market analysis toggles too. Set `run.json.lang` to change the default.

1. **Fetch** what they asked to see: Markets → **the 50 most-traded markets in the last 24h** (pass them
   as the `universe` pool — `build_data.py` ranks by `volume_24h` and takes the top 50), enriched via MCP
   `get_order_book_depth` / `get_price_history` / `get_market_stats` for depth / OHLC candles / flow;
   Recommendations → your own analysis (a separate tab — not merged into Markets); Account → `clob balance`,
   `data value`, `data positions`, `clob orders`, `clob trades`, `wallet show` (skip and set
   `account: null` if no key is configured).
2. **Build** one `DATA` object (schema in artifacts.md). Keep numbers as the Decimal strings the sources
   return; stamp `meta.generated_at` = now. Unfetched lists → `[]`, skipped objects → `null`.
3. **Inject** — read [assets/dashboard-template.html](assets/dashboard-template.html), replace only the
   `POLYMARKET_DATA_START…END` block with your `const DATA = {…}`, emit the file as the artifact.
4. **Caveat**: the dashboard is a snapshot frozen at `generated_at`; tell the user to regenerate for
   fresh data. Always render through this template — don't hand-roll one-off dashboard HTML.
