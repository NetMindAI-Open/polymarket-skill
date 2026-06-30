"""Bridge: turn an opportunity-scan run into the dashboard artifact's DATA object.

Deterministic + stdlib-only so it runs with a plain `python3` and is unit-testable
(mirrors risk_gate.py). It does NOT fetch anything — the orchestrator passes in the
universe, the gated opportunities, the per-market enrichment, and (optionally) account
data; this maps them into the `DATA` schema in reference/artifacts.md and (optionally)
injects it into assets/dashboard-template.html to emit the finished artifact.

Input (JSON on stdin):
  {
    "universe":      [ {condition_id, slug, question, yes_price, volume_24h, liquidity,
                        spread, best_bid, best_ask, price_change_pct,
                        token_id_yes, token_id_no, event_id}, ... ],
    "opportunities": [ {strategy, condition_id, slug, token_id, outcome, thesis,
                        proposed_action:{side,order_type,price,size_usd}, edge_estimate,
                        confidence, liquidity_check:{...}, risks:[...], signal:{...},
                        gate:{decision:"auto"|"escalate"|"skip", order_id?}}, ... ],
    "enrichment":    { "<condition_id>": {url, category, end_date, description,
                        volume_total, net_flow, depth, candles} },   # for the shown markets
    "account":       {...} | null,   # null/empty when no wallet is set up -> Account tab shows setup steps
    "generated_at":  "<UTC ISO>",
    "wallet_label":  "deposit 0x…",
    "stats":         {...} | null   # optional override of the stats strip
  }

Usage:
    python3 assets/build_data.py < payload.json                       # prints DATA json
    python3 assets/build_data.py --inject assets/dashboard-template.html < payload.json   # prints filled HTML
"""
import json
import re
import sys

# gate decision -> recommendation status pill
_STATUS = {"auto": "executed", "escalate": "pending", "skip": "skipped"}

# The Markets tab is simply the most-traded markets in the last 24h: rank the pool by 24h
# volume and show the top MARKETS_LIMIT (or all of them, if the pool is smaller).
MARKETS_LIMIT = 50

# Liveness floor: markets quoting a YES probability at or below this (resolved / dead longshots
# sitting near 0) are dropped. Top-by-volume rarely hits these, but it keeps the grid clean.
MIN_YES_PRICE = 0.01

# Plain-language, user-facing one-liners shown on the recommendation cards. The full specs
# live in reference/strategies/*.md; these are the short "what is this play" gloss so a reader
# understands *why it's an opportunity* without opening the spec.
STRATEGY_NOTES = {
    "momentum": "rides a strong recent price move, betting the trend keeps going",
    "mean-reversion": "bets a sharp overshoot snaps back toward its recent average",
    "spread-capture": "earns the gap between the buy and sell price by posting resting orders",
    "smart-money": "follows large, one-directional buying that looks informed",
    "risk-free-arb": "locks a guaranteed profit when YES + NO together cost less than $1",
    "multi-outcome-arb": "locks a profit when a market's outcomes price below $1 in total",
}

# Why the risk gate set an opportunity aside — plain-language version of decide()'s reason
# codes (keys must match risk_gate.py exactly). Turns "insufficient book depth at price" into
# something a reader understands as a *risk*, not a code.
GATE_REASON_NOTES = {
    "confidence below report floor": "the signal was too weak to act on",
    "market liquidity below floor": "too little money resting in this market to trade our size safely",
    "insufficient book depth at price": "not enough resting orders at the target price, so filling would push the price against us",
    "order notional over per-order cap": "the proposed order is larger than the per-trade limit",
    "would breach per-run total cap": "buying it would push this scan past its total budget for the run",
    "order would take too much resting depth": "the order would eat too large a share of the visible order book",
}

# Skipped/WATCH cards still sit in the "low" band, but show a small non-zero meter purely for
# UX (an empty bar reads as broken). Intentionally loose: a stronger-but-gated candidate gets
# 3 of 10 segments, a weak one gets 2 — the meter is a vibe, not a measurement.
SKIP_METER_STRONG = "0.3"   # ~3 of 10 segments
SKIP_METER_WEAK = "0.2"     # ~2 of 10 segments


def _s(v):
    """Stringify the way the template expects (decimal strings), leaving None as None."""
    if v is None:
        return None
    if isinstance(v, str):
        return v
    if isinstance(v, float):
        return repr(v)
    return str(v)


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _is_live(u):
    """True if a market's YES probability clears MIN_YES_PRICE (filters dead/resolved markets)."""
    return _num(u.get("yes_price")) > MIN_YES_PRICE


def _compact(v):
    n = abs(_num(v))
    if n >= 1e9:
        return "%.1fB" % (n / 1e9)
    if n >= 1e6:
        return "%.1fM" % (n / 1e6)
    if n >= 1e3:
        return "%.1fk" % (n / 1e3)
    return str(int(n))


def confidence_band(c):
    """Match the risk gate's thresholds: >=0.75 high, >=0.5 medium, else low."""
    c = _num(c)
    return "high" if c >= 0.75 else "medium" if c >= 0.5 else "low"


def market_from_universe(u, enrich):
    """Map a universe row (+ optional enrichment) into a markets[] entry."""
    m = {
        "question": u.get("question"),
        "slug": u.get("slug"),
        "condition_id": u.get("condition_id"),
        "yes_token_id": _s(u.get("token_id_yes")),
        "no_token_id": _s(u.get("token_id_no")),
        "yes_price": _s(u.get("yes_price")),
        "volume_24h": _s(u.get("volume_24h")),
        "liquidity": _s(u.get("liquidity")),
    }
    # merge enrichment: real event-slug url, category, end_date, description, volume_total, net_flow, depth, candles
    for k in ("url", "category", "end_date", "description", "volume_total", "net_flow", "depth", "candles"):
        if enrich and enrich.get(k) is not None:
            m[k] = enrich[k]
    return m


def opportunity_to_recommendation(opp, universe_by_cond, enrich):
    """Map a gated Opportunity into a recommendations[] entry.

    A gate `skip` is no longer hidden: it is surfaced as a low-confidence
    *watch* item whose first signal is the gate's reason, so the user still sees
    the candidate and *why* it was set aside. `auto`/`escalate` keep their own
    confidence band and meter.
    """
    cond = opp.get("condition_id")
    u = universe_by_cond.get(cond, {})
    gate = opp.get("gate") or {}
    status = _STATUS.get(gate.get("decision", "escalate"), "pending")
    skipped = status == "skipped"
    side = (opp.get("proposed_action") or {}).get("side", "BUY").upper()
    action = "WATCH" if skipped else side

    signals = []
    lc = opp.get("liquidity_check") or {}
    if lc.get("market_liquidity_usd"):
        signals.append("liq $" + _compact(lc["market_liquidity_usd"]))
    if lc.get("est_slippage") is not None:
        signals.append("slippage " + _s(lc["est_slippage"]))
    for key, val in (opp.get("signal") or {}).items():
        signals.append("%s %s" % (key, val))
    for risk in (opp.get("risks") or []):
        signals.append(risk)

    rec = {
        "question": u.get("question") or opp.get("slug"),
        "slug": opp.get("slug"),
        "outcome": (opp.get("outcome") or "yes").upper(),
        "action": action,
        # skip -> forced "low" band; the meter below is a small fixed UX fill, not the raw score
        "confidence": "low" if skipped else confidence_band(opp.get("confidence")),
        "rationale": opp.get("thesis"),
        "signals": signals[:5],
        "strategy": opp.get("strategy"),
        "status": status,
    }
    if skipped:
        rec["confidence_score"] = SKIP_METER_STRONG if _num(opp.get("confidence")) >= 0.5 else SKIP_METER_WEAK
    else:
        rec["confidence_score"] = _s(opp.get("confidence"))
    # what the play is (every card) + why the gate set it aside (skipped only) — plain language
    note = STRATEGY_NOTES.get(opp.get("strategy"))
    if note:
        rec["strategy_note"] = note
    if skipped:
        reason = gate.get("reason")
        rec["gate_note"] = GATE_REASON_NOTES.get(reason, reason) if reason else "set aside by the risk gate"
    price = (opp.get("proposed_action") or {}).get("price")
    if price is not None:
        rec["target_price"] = _s(price)
    size = (opp.get("proposed_action") or {}).get("size_usd")
    if size is not None:
        rec["size_usd"] = _s(size)
    if opp.get("edge_estimate"):
        rec["edge"] = opp["edge_estimate"]
    if gate.get("order_id"):
        rec["order_id"] = gate["order_id"]
    if enrich and enrich.get("url"):
        rec["url"] = enrich["url"]
    return rec


def compute_stats(universe):
    """Stats strip from the FULL universe (not just the injected subset)."""
    tot = v24 = liq = 0.0
    for u in universe:
        v24 += _num(u.get("volume_24h"))
        liq += _num(u.get("liquidity"))
        tot += _num(u.get("volume_total") if u.get("volume_total") is not None else u.get("volume_24h"))
    return {"total_volume": str(int(tot)), "volume_24h": str(int(v24)),
            "liquidity": str(int(liq)), "active": len(universe)}


def build_data(payload):
    universe = payload.get("universe") or []
    opps = payload.get("opportunities") or []
    enrichment = payload.get("enrichment") or {}
    by_cond = {u.get("condition_id"): u for u in universe}

    # Markets tab = the most-traded markets in the last 24h, plain and simple: drop dead
    # markets (YES <= MIN_YES_PRICE), rank the pool by 24h volume, take the top MARKETS_LIMIT.
    # Recommendations live in their own tab and are NOT forced into this grid.
    ranked = sorted((u for u in universe if _is_live(u)),
                    key=lambda u: _num(u.get("volume_24h")), reverse=True)
    markets = [market_from_universe(u, enrichment.get(u.get("condition_id")))
               for u in ranked[:MARKETS_LIMIT]]

    recommendations = [opportunity_to_recommendation(o, by_cond, enrichment.get(o.get("condition_id"))) for o in opps]

    return {
        "meta": {
            "generated_at": payload.get("generated_at"),
            "wallet_label": payload.get("wallet_label", "no wallet"),
            "currency": "USDC",
            "stats": payload.get("stats") or compute_stats(universe),
        },
        "markets": markets,
        "recommendations": recommendations,
        # null when the wallet isn't set up (orchestrator passes account only if a key is
        # configured) -> the dashboard's Account tab renders wallet-setup steps. Coerce an
        # empty {} to null too, so a blank account never renders as a zeroed-out balance.
        "account": payload.get("account") or None,
    }


# whole block: START marker comment … const DATA = {…}; … END marker comment
_DATA_BLOCK = re.compile(
    r"/\* === POLYMARKET_DATA_START.*?POLYMARKET_DATA_END === \*/",
    re.DOTALL,
)


def inject(template_html, data):
    """Replace the template's DATA block with the generated DATA object."""
    body = ("/* === POLYMARKET_DATA_START — generated by build_data.py === */\n"
            "const DATA = " + json.dumps(data, ensure_ascii=False, indent=2) + ";\n"
            "/* === POLYMARKET_DATA_END === */")
    # function replacement → returned string is used literally (no backslash/group processing)
    new, n = _DATA_BLOCK.subn(lambda _m: body, template_html)
    if n != 1:
        raise SystemExit("error: expected exactly one POLYMARKET_DATA block, found %d" % n)
    return new


def main(argv):
    inject_path = None
    if len(argv) >= 2 and argv[0] == "--inject":
        inject_path = argv[1]
    payload = json.load(sys.stdin)
    data = build_data(payload)
    if inject_path:
        with open(inject_path) as fh:
            html = fh.read()
        sys.stdout.write(inject(html, data))
    else:
        sys.stdout.write(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main(sys.argv[1:])
