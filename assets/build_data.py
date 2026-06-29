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
                        volume_total, net_flow, depth, candles} },   # for the curated subset
    "account":       {...} | null,   # null/empty when no wallet is set up -> Account tab shows setup steps
    "top_n":         24,            # extra top-volume universe markets to include beyond the rec'd ones
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
    """Map a gated Opportunity into a recommendations[] entry."""
    cond = opp.get("condition_id")
    u = universe_by_cond.get(cond, {})
    gate = opp.get("gate") or {}
    status = _STATUS.get(gate.get("decision", "escalate"), "pending")
    side = (opp.get("proposed_action") or {}).get("side", "BUY").upper()
    action = "WATCH" if status == "skipped" else side

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
        "confidence": confidence_band(opp.get("confidence")),
        "confidence_score": _s(opp.get("confidence")),
        "rationale": opp.get("thesis"),
        "signals": signals[:5],
        "strategy": opp.get("strategy"),
        "status": status,
    }
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
    top_n = int(payload.get("top_n", 30))
    by_cond = {u.get("condition_id"): u for u in universe}

    # curated subset = every recommended market first, then top-N universe by 24h volume
    rec_conds = [o.get("condition_id") for o in opps if o.get("condition_id")]
    ranked = sorted(universe, key=lambda u: _num(u.get("volume_24h")), reverse=True)
    target = len(set(rec_conds)) + top_n
    chosen, seen = [], set()
    for cond in rec_conds + [u.get("condition_id") for u in ranked]:
        if cond and cond not in seen and cond in by_cond:
            seen.add(cond)
            chosen.append(by_cond[cond])
        if len(chosen) >= target:
            break

    markets = [market_from_universe(u, enrichment.get(u.get("condition_id"))) for u in chosen]

    # Enrich the grid with the most-traded markets in the last 24h (popularity, not anomaly).
    # The scouted universe is a filtered/anomaly set; `trending` is a separate broad list the
    # orchestrator pulls and ranks by 24h volume. Merge it in, deduped by condition_id, tagged
    # so the template's category-driven chip/tag surfaces it with no template change.
    trending = payload.get("trending") or []
    trending_n = int(payload.get("trending_n", 12))
    trending_top = sorted(trending, key=lambda u: _num(u.get("volume_24h")), reverse=True)[:trending_n]
    market_by_cond = {m.get("condition_id"): m for m in markets}
    for u in trending_top:
        cond = u.get("condition_id")
        if not cond:
            continue
        existing = market_by_cond.get(cond)
        if existing is not None:
            existing["trending"] = True            # already shown (also scouted) -> just flag it
            continue
        m = market_from_universe(u, enrichment.get(cond))
        m["trending"] = True
        m.setdefault("category", "🔥 Trending")     # no real category -> category-driven chip/tag for free
        markets.append(m)
        market_by_cond[cond] = m

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
