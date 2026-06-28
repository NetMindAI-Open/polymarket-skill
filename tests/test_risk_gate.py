import risk_gate


def base_opp():
    return {
        "strategy": "risk-free-arb",
        "condition_id": "0x1",
        "slug": "s",
        "token_id": "t",
        "outcome": "yes",
        "thesis": "x",
        "proposed_action": {"side": "BUY", "order_type": "limit", "price": 0.5, "size_usd": 8},
        "confidence": 0.9,
        "liquidity_check": {"market_liquidity_usd": 20000, "depth_usd_at_price": 100},
    }


CFG = risk_gate.DEFAULTS


def test_structural_arb_within_caps_auto_executes():
    assert risk_gate.decide(base_opp(), CFG, 0)["decision"] == "auto"


def test_directional_strategy_always_escalates():
    opp = base_opp()
    opp["strategy"] = "momentum"
    assert risk_gate.decide(opp, CFG, 0)["decision"] == "escalate"


def test_structural_arb_low_confidence_escalates():
    opp = base_opp()
    opp["confidence"] = 0.6  # >= report floor, < auto floor
    assert risk_gate.decide(opp, CFG, 0)["decision"] == "escalate"


def test_below_report_floor_skips():
    opp = base_opp()
    opp["confidence"] = 0.4
    d = risk_gate.decide(opp, CFG, 0)
    assert d["decision"] == "skip"
    assert "report floor" in d["reason"]


def test_low_market_liquidity_skips():
    opp = base_opp()
    opp["liquidity_check"]["market_liquidity_usd"] = 1000
    assert risk_gate.decide(opp, CFG, 0)["decision"] == "skip"


def test_insufficient_depth_skips():
    opp = base_opp()
    opp["liquidity_check"]["depth_usd_at_price"] = 10  # need >= 2*8=16
    assert risk_gate.decide(opp, CFG, 0)["decision"] == "skip"


def test_over_per_order_cap_skips():
    opp = base_opp()
    opp["proposed_action"]["size_usd"] = 11  # cap 10
    opp["liquidity_check"]["depth_usd_at_price"] = 1000
    assert risk_gate.decide(opp, CFG, 0)["decision"] == "skip"


def test_over_run_total_skips():
    # size 8, run_total 45, cap 50 -> 53 > 50
    assert risk_gate.decide(base_opp(), CFG, 45)["decision"] == "skip"


def test_book_take_pct_skips():
    opp = base_opp()
    opp["proposed_action"]["size_usd"] = 9
    opp["liquidity_check"]["depth_usd_at_price"] = 20  # 9/20=45% > 25%, depth ok (>=18)
    d = risk_gate.decide(opp, CFG, 0)
    assert d["decision"] == "skip"
    assert "resting depth" in d["reason"]


def test_at_run_total_boundary_is_allowed():
    # size 8, run_total 42, cap 50 -> 50 not > 50 -> not skipped
    assert risk_gate.decide(base_opp(), CFG, 42)["decision"] == "auto"
