import json
from pathlib import Path

import risk_gate

FIXTURE = Path(__file__).parent / "fixtures" / "opportunity.valid.json"


def _valid():
    return json.loads(FIXTURE.read_text())


def test_valid_opportunity_passes():
    assert risk_gate.validate_opportunity(_valid()) == []


def test_missing_required_field_fails():
    obj = _valid()
    del obj["confidence"]
    errors = risk_gate.validate_opportunity(obj)
    assert errors
    assert any("confidence" in e for e in errors)


def test_bad_outcome_enum_fails():
    obj = _valid()
    obj["outcome"] = "maybe"
    assert risk_gate.validate_opportunity(obj)


def test_confidence_out_of_range_fails():
    obj = _valid()
    obj["confidence"] = 1.5
    assert risk_gate.validate_opportunity(obj)


def test_limit_order_without_price_fails():
    obj = _valid()
    obj["proposed_action"]["order_type"] = "limit"
    obj["proposed_action"].pop("price", None)
    errors = risk_gate.validate_opportunity(obj)
    assert errors
    assert any("price" in e for e in errors)


def test_market_order_without_price_passes():
    obj = _valid()
    obj["proposed_action"]["order_type"] = "market"
    obj["proposed_action"].pop("price", None)
    assert risk_gate.validate_opportunity(obj) == []
