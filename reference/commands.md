# `poly` command reference (agent-facing)

Every command the `poly` CLI exposes, with options, a **read/write** tag, and the JSON shapes you get
back. Upstream source of truth: the CLI's own `docs/COMMANDS.md` — keep this in sync when the CLI changes.

Conventions:
- Global options go **before** the subcommand: `poly [GLOBAL] COMMAND [ARGS]`.
- `-o json` / `--output json` returns full fields; always use it when driving the CLI programmatically.
- `--private-key TEXT` overrides the signer key for one run. Resolution order otherwise:
  `--private-key` → `POLYMARKET_PRIVATE_KEY` env → `~/.config/polymarket/config.json`.
- Exit code: `0` success, `1` failure. On failure with `-o json`, output is `{"error": "<message>"}`.
- **Two addresses:** *signer EOA* (signs orders, normally empty) vs *deposit wallet* (SDK-derived proxy
  that holds USDC + positions; what polymarket.com shows). Funds/approvals live on the deposit wallet.

---

## Setup & wallet — WRITE (local config only)

Backed by `~/.config/polymarket/config.json` (`chmod 600`). Keys are never printed.
**Configuring a key does NOT make a brand-new wallet trade-ready** — see [recipes.md](recipes.md)
"Activate a brand-new wallet".

| Command | Args / options | Notes |
|---|---|---|
| `setup` | `--private-key TEXT` (optional; else hidden prompt) | First-time key config. |
| `wallet create` | `--force` (overwrite existing) | Generate a brand-new random wallet. **Never used on Polymarket → must be activated before trading.** |
| `wallet import <PRIVATE_KEY>` | `<PRIVATE_KEY>` required arg | Import an existing key. |
| `wallet show` | — | **READ.** Signer EOA + deposit wallet + config path. |
| `wallet address` | — | **READ.** Deposit wallet address only. |
| `wallet reset` | `--force` (required to delete) | Delete saved config. |

---

## Market discovery (`markets`) — READ (public, no key needed)

Returns `question`, `yes_price`, `slug` in table mode; `-o json` adds `condition_id`, `yes_token_id`,
`no_token_id`.

| Command | Args / options | Notes |
|---|---|---|
| `markets search <QUERY>` | `<QUERY>` required; `--limit INT` (default 20) | Keyword search across events + markets. |
| `markets get <REF>` | `<REF>` = id, slug, or URL (auto-detected) | Single market. |
| `markets list` | `--limit INT` (default 20); `--closed`/`--active` (default active) | List open or resolved markets. |

> **Event slug ≠ market slug.** `fifwc-tur-usa-2026-06-25` is an *event* with several markets
> (`…-usa`, `…-tur`, `…-draw`). Trading needs the **market** slug — drill down via search/get.

JSON shape (search/list = array; get = object):
```json
[{"question": "...", "slug": "...", "condition_id": "0x...", "yes_price": "0.65",
  "yes_token_id": "12345", "no_token_id": "12346"}]
```

---

## Trading — WRITE (spends real USDC)

`buy`/`sell` are aliases: without `--market` = limit order (`clob create-order`); with `--market` =
market order (`clob market-order`). All build + sign + preview, then require a typed `YES` unless
`--yes`. `--dry-run` previews without submitting (and needs no confirmation).

### `buy` / `sell` (identical options)

| Option | Req | Default | Meaning |
|---|---|---|---|
| `--token-id`/`--token TEXT` \| `--slug TEXT` \| `--url TEXT` | exactly one | — | What to trade. |
| `--outcome TEXT` | optional | `yes` | `yes`/`no`; ignored with `--token-id`. |
| `--usd TEXT` \| `--size TEXT` | one | — | Limit: `--usd` (size = usd÷price, floored) or `--size`. Market: **BUY needs `--usd`**, **SELL needs `--size`**. |
| `--price TEXT` | limit only | — | Per-share price, strictly 0–1, rounded to tick. Required for limit. |
| `--market` | optional | off | Market order instead of limit. |
| `--max-spend TEXT` | optional | = `--usd` | Market BUY fee-inclusive USD cap. |
| `--dry-run` | optional | off | Build + sign + preview only; never submits. |
| `--yes` | optional | off | Skip the typed-`YES` confirmation (required for autonomous submit). |

```bash
poly -o json buy  --slug <market-slug> --outcome yes --usd 1 --price 0.5 --dry-run
poly -o json sell --token-id 472367... --size 10 --price 0.4 --yes
poly -o json buy  --url https://polymarket.com/event/... --outcome yes --usd 2 --market --yes
```

### `clob create-order` (explicit limit) / `clob market-order` (explicit market)

Same targets as above. `create-order`: `--side BUY|SELL` (required), `--price` (required), `--size`/`--usd`.
`market-order`: `--side` (required), `--usd` (BUY) / `--size` (SELL), `--max-spend`, `--order-type FAK|FOK`
(default `FAK`). Both take `--dry-run` and `--yes`.

### `clob post-orders` — batch limit orders

All required, comma-separated, positionally aligned: `--tokens`, `--side`, `--prices`, `--sizes`.
```bash
poly -o json clob post-orders --tokens 111,222 --side BUY --prices 0.4,0.6 --sizes 10,5
```

**With `-o json`, trade commands print TWO objects: a preview, then the result/dry-run.**

Preview (always printed first):
```json
{"market": "Will ...?", "outcome": "Yes", "condition": "0x...", "side": "BUY",
 "token_id": "275777...", "wallet": "0x...", "order": "limit / GTC",
 "price": "0.5 USDC/share", "size": "2 shares", "~notional": "1 USDC", "book_price": "0.61 (BUY)"}
```
Then, on a real submit — the result:
```json
{"result": "ACCEPTED  order_id=0x...  status=PENDING"}   // exit 0
{"result": "REJECTED  code=INVALID_PRICE  message=..."}  // exit 1
```
Or, with `--dry-run` — the signed order (no submission; amounts are integer base units, 6-decimal USDC):
```json
{"dry_run": true, "maker": "0x...", "signer": "0x...", "token_id": "275777...", "side": "BUY",
 "maker_amount": 1000000, "taker_amount": 2000000, "order_type": "GTC",
 "signature_type": 3, "expiration": 0, "wallet": "0x..."}
```

---

## Order management (`clob`) — mostly WRITE (cancels); listing is READ

| Command | Args / options | R/W | Notes |
|---|---|---|---|
| `clob orders` | `--market TEXT` (filter by condition id) | READ | Your open orders. |
| `clob order <ORDER_ID>` | required arg | READ | One order's details. |
| `clob cancel <ORDER_ID>` | required arg | WRITE | Cancel one order. |
| `clob cancel-orders <IDS>` | comma-separated arg | WRITE | Cancel several. |
| `clob cancel-market --market <ID>` | required | WRITE | Cancel all in one market. |
| `clob cancel-all` | `--yes` (skip prompt) | WRITE | Cancel **all** open orders. Typed-`YES` unless `--yes`. |

---

## Account & balances — READ

| Command | Args / options | Notes |
|---|---|---|
| `clob balance --asset-type <collateral\|conditional>` | `--token TEXT` (required for `conditional`) | Human units + `raw` base units. |
| `clob trades` | — | Account trade history. |
| `data positions [ADDRESS]` | `--limit INT` (default 20) | Positions; ADDRESS defaults to your deposit wallet. |
| `data value [ADDRESS]` | — | Portfolio value; defaults to your deposit wallet. |

**Balance JSON:**
```json
{"asset_type": "COLLATERAL", "balance": "1234.567", "raw": "1234567000"}
```

---

## Gotchas

- **Configuring a key ≠ trade-ready.** A brand-new wallet must be activated on polymarket.com (login →
  deposit USDC → "Enable Trading" approvals). See [recipes.md](recipes.md). Unactivated wallets pass
  `--dry-run` but fail live with `InsufficientAllowanceError`.
- **Signer EOA vs deposit wallet** — `wallet address`, `data positions/value`, and balances use the
  **deposit wallet** (holds funds). The EOA only signs and is normally empty.
- **`--dry-run` is a signing check, not a readiness check.** It always succeeds if the order is valid.
- **Market-order side semantics** — BUY spends `--usd`; SELL delivers `--size`. Mixing is rejected.
