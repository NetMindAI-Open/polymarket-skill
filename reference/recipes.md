# Recipes

Copy-pasteable multi-step workflows. All use `-o json`; check the exit code (`0` ok / `1` fail) and
parse `{"error": …}` on failure. Full flag detail: [commands.md](commands.md).

---

## Find a market and check the odds

```bash
poly -o json markets search "world cup final" --limit 10
# pick the right MARKET slug from the results (not the event), then:
poly -o json markets get <market-slug>
```
Use `yes_token_id` / `no_token_id` from the JSON to trade a specific outcome by token id.

---

## Buy an outcome (limit), preview first

```bash
# 1) preview — builds + signs locally, does NOT submit
poly -o json buy --slug <market-slug> --outcome yes --usd 5 --price 0.42 --dry-run
# 2) inspect the dry-run JSON (wallet, size, side); if good, submit autonomously:
poly -o json buy --slug <market-slug> --outcome yes --usd 5 --price 0.42 --yes
# -> {"result": "ACCEPTED  order_id=...  status=..."}  (exit 0)  | REJECTED (exit 1)
```

## Market buy (spend a fixed USD amount)

```bash
poly -o json buy --slug <market-slug> --outcome yes --usd 10 --market --max-spend 10 --yes
```
Market **BUY** spends `--usd`; market **SELL** uses `--size` (shares).

---

## Check my account

```bash
poly -o json clob balance --asset-type collateral     # USDC cash
poly -o json data positions                           # open positions (deposit wallet)
poly -o json data value                               # portfolio value
poly -o json clob orders                               # my open orders
```

## Cancel orders

```bash
poly -o json clob orders --market <condition-id>      # find ids
poly -o json clob cancel <order-id>                   # one
poly -o json clob cancel-market --market <condition-id>   # all in a market
poly -o json clob cancel-all --yes                    # everything (skips prompt)
```

---

## Activate a brand-new wallet (do this before its first live trade)

**Importing or creating a key only configures signing.** A wallet that has never been used on Polymarket
is not trade-ready. Configure the key, then activate it on the website.

```bash
# configure the signing key (pick one)
poly setup                          # hidden prompt
poly wallet import 0x<key>          # non-interactive
poly wallet create                  # brand-new random wallet (definitely needs activation)

# confirm which deposit wallet this key controls
poly -o json wallet show            # note the deposit wallet address
```

Then tell the user to do this **on polymarket.com** (the agent cannot do these for them):

> 1. Connect/log in with this wallet at **polymarket.com** (import the key into MetaMask → Connect, or
>    use the email/Magic login that owns it).
> 2. **Deposit USDC** — funds land on the **deposit wallet** (the address from `wallet show`), not the
>    signer EOA.
> 3. Complete the on-screen **"Enable Trading" approvals** — deploys the proxy/deposit wallet and grants
>    USDC + CTF allowances. Easiest on the website (gasless).

Verify readiness before trading:

```bash
poly -o json wallet show                              # deposit wallet == polymarket.com/settings?
poly -o json clob balance --asset-type collateral     # USDC funded?
```

If a live order returns `InsufficientAllowanceError`, activation/approvals are not complete — stop and
have the user finish the website steps above. A passing `--dry-run` does **not** prove readiness.
