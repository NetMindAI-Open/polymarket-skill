"""Risk-gate decision core + Opportunity validation for the Polymarket scanner.

decide() is stdlib-only so it runs with a plain `python3`. validate_opportunity()
imports jsonschema lazily (run it via `uv run --with jsonschema ...`).
"""
import json
from pathlib import Path

_SCHEMA_PATH = Path(__file__).parent.parent / "reference" / "opportunity.schema.json"


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
