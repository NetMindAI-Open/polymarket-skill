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
