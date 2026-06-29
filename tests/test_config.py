import json

import risk_gate


def test_missing_file_returns_defaults(tmp_path):
    cfg = risk_gate.load_config(str(tmp_path / "nope.json"))
    assert cfg == risk_gate.DEFAULTS
    # must be a copy, not the same object
    assert cfg is not risk_gate.DEFAULTS


def test_partial_file_merges_over_defaults(tmp_path):
    p = tmp_path / "agent.json"
    p.write_text(json.dumps({"max_total_per_run_usd": 30}))
    cfg = risk_gate.load_config(str(p))
    assert cfg["max_total_per_run_usd"] == 30
    assert cfg["max_notional_per_order_usd"] == 10  # default preserved


def test_defaults_have_expected_values():
    d = risk_gate.DEFAULTS
    assert d["max_notional_per_order_usd"] == 10
    assert d["max_total_per_run_usd"] == 50
    assert d["min_confidence_auto"] == 0.75
    assert d["min_confidence_report"] == 0.5
    assert d["min_liquidity_usd"] == 5000
    assert d["min_depth_multiple"] == 2
    assert d["max_book_take_pct"] == 25
    assert d["auto_execute_strategies"] == ["risk-free-arb", "multi-outcome-arb"]
