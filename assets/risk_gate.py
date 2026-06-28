"""Risk-gate decision core + Opportunity validation for the Polymarket scanner.

decide() is stdlib-only so it runs with a plain `python3`. validate_opportunity()
imports jsonschema lazily (run it via `uv run --with jsonschema ...`).
"""
import copy
import json
import os
from pathlib import Path

_SCHEMA_PATH = Path(__file__).parent.parent / "reference" / "opportunity.schema.json"

DEFAULTS = {
    "max_notional_per_order_usd": 10,
    "max_total_per_run_usd": 50,
    "min_confidence_auto": 0.75,
    "min_confidence_report": 0.5,
    "min_liquidity_usd": 5000,
    "min_depth_multiple": 2,
    "max_book_take_pct": 25,
    "auto_execute_strategies": ["risk-free-arb", "multi-outcome-arb"],
}

_DEFAULT_CONFIG_PATH = "~/.config/polymarket/agent.json"


def load_config(path=None):
    """Return DEFAULTS merged with the JSON config file (file wins). Missing file -> DEFAULTS copy."""
    cfg = copy.deepcopy(DEFAULTS)
    resolved = os.path.expanduser(path or _DEFAULT_CONFIG_PATH)
    if os.path.isfile(resolved):
        with open(resolved) as fh:
            cfg.update(json.load(fh))
    return cfg


def validate_opportunity(obj):
    """Return a list of error strings; empty list means valid."""
    import jsonschema

    schema = json.loads(_SCHEMA_PATH.read_text())
    validator = jsonschema.Draft7Validator(schema)
    errors = []
    for err in validator.iter_errors(obj):
        loc = "/".join(str(p) for p in err.path) or "(root)"
        errors.append(f"{loc}: {err.message}")
    return errors


def decide(opportunity: dict, config: dict, run_total_usd: float) -> dict:
    """Return {"decision": "auto"|"escalate"|"skip", "reason": str}.

    Applies 8 decision checks in strict order; first match wins.
    """
    pa = opportunity["proposed_action"]
    lc = opportunity["liquidity_check"]
    size = pa["size_usd"]
    conf = opportunity["confidence"]
    strat = opportunity["strategy"]
    mkt_liq = lc.get("market_liquidity_usd", 0)
    depth = lc.get("depth_usd_at_price", 0)

    def result(decision, reason):
        return {"decision": decision, "reason": reason}

    # Check 1: confidence < min_confidence_report
    if conf < config["min_confidence_report"]:
        return result("skip", "confidence below report floor")

    # Check 2: market liquidity below floor
    if mkt_liq < config["min_liquidity_usd"]:
        return result("skip", "market liquidity below floor")

    # Check 3: insufficient book depth
    if depth < config["min_depth_multiple"] * size:
        return result("skip", "insufficient book depth at price")

    # Check 4: over per-order cap
    if size > config["max_notional_per_order_usd"]:
        return result("skip", "order notional over per-order cap")

    # Check 5: would breach per-run cap
    if run_total_usd + size > config["max_total_per_run_usd"]:
        return result("skip", "would breach per-run total cap")

    # Check 6: takes too much resting depth
    if depth > 0 and (size / depth) * 100 > config["max_book_take_pct"]:
        return result("skip", "order would take too much resting depth")

    # Check 7: auto-execute if structural arb with high confidence
    if strat in config["auto_execute_strategies"] and conf >= config["min_confidence_auto"]:
        return result("auto", "structural arb within caps and confident")

    # Check 8: otherwise escalate
    return result("escalate", "requires human confirmation")
