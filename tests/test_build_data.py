import json
from pathlib import Path

import build_data

TEMPLATE = Path(__file__).parent.parent / "assets" / "dashboard-template.html"


def universe():
    return [
        {"condition_id": "0xA", "slug": "arb-mkt", "question": "Arb market?", "yes_price": "0.48",
         "volume_24h": "50000", "liquidity": "20000", "token_id_yes": "111", "token_id_no": "112"},
        {"condition_id": "0xB", "slug": "big-mkt", "question": "Big market?", "yes_price": "0.30",
         "volume_24h": "900000", "liquidity": "80000", "volume_total": "5000000",
         "token_id_yes": "211", "token_id_no": "212"},
        {"condition_id": "0xC", "slug": "small-mkt", "question": "Small market?", "yes_price": "0.10",
         "volume_24h": "1000", "liquidity": "3000", "token_id_yes": "311", "token_id_no": "312"},
    ]


def opp(decision="auto"):
    return {
        "strategy": "risk-free-arb", "condition_id": "0xA", "slug": "arb-mkt", "token_id": "111",
        "outcome": "yes", "thesis": "YES+NO under 1.00 locks 3%.",
        "proposed_action": {"side": "BUY", "order_type": "limit", "price": 0.48, "size_usd": 8},
        "edge_estimate": "3 cents / ~3%", "confidence": 0.9,
        "liquidity_check": {"market_liquidity_usd": 20000, "depth_usd_at_price": 50, "est_slippage": 0.001},
        "signal": {"sum_of_outcomes": 0.97}, "risks": ["resolution dispute"],
        "gate": {"decision": decision, "order_id": "0xORDER" if decision == "auto" else None},
    }


def mkt(cond, yes, vol, liq="10000"):
    return {"condition_id": cond, "slug": cond, "question": f"{cond}?",
            "yes_price": yes, "volume_24h": vol, "liquidity": liq,
            "token_id_yes": f"{cond}y", "token_id_no": f"{cond}n"}


# ---- confidence banding matches the risk gate thresholds ----
def test_confidence_band():
    assert build_data.confidence_band(0.9) == "high"
    assert build_data.confidence_band(0.75) == "high"
    assert build_data.confidence_band(0.6) == "medium"
    assert build_data.confidence_band(0.4) == "low"


# ---- opportunity -> recommendation mapping (Recommendations tab, separate from Markets) ----
def test_gate_decision_maps_to_status():
    by = {u["condition_id"]: u for u in universe()}
    assert build_data.opportunity_to_recommendation(opp("auto"), by, None)["status"] == "executed"
    assert build_data.opportunity_to_recommendation(opp("escalate"), by, None)["status"] == "pending"
    assert build_data.opportunity_to_recommendation(opp("skip"), by, None)["status"] == "skipped"


def test_recommendation_fields():
    by = {u["condition_id"]: u for u in universe()}
    rec = build_data.opportunity_to_recommendation(opp("auto"), by, {"url": "https://polymarket.com/event/arb-mkt"})
    assert rec["question"] == "Arb market?"          # joined from universe
    assert rec["outcome"] == "YES"                    # upper-cased
    assert rec["action"] == "BUY"
    assert rec["confidence"] == "high"
    assert rec["confidence_score"] == "0.9"
    assert rec["target_price"] == "0.48"
    assert rec["size_usd"] == "8"
    assert rec["strategy"] == "risk-free-arb"
    assert rec["order_id"] == "0xORDER"
    assert rec["url"] == "https://polymarket.com/event/arb-mkt"
    assert "resolution dispute" in rec["signals"]


def test_skipped_action_is_watch():
    by = {u["condition_id"]: u for u in universe()}
    assert build_data.opportunity_to_recommendation(opp("skip"), by, None)["action"] == "WATCH"


# ---- skipped opps are surfaced (not dropped) as low-confidence watch items ----
def test_skipped_surfaced_as_low_confidence_with_reason():
    by = {u["condition_id"]: u for u in universe()}
    o = opp("skip")                                    # raw confidence 0.9, but gated out
    o["gate"]["reason"] = "market liquidity below floor"
    rec = build_data.opportunity_to_recommendation(o, by, None)
    assert rec["status"] == "skipped"
    assert rec["action"] == "WATCH"
    assert rec["confidence"] == "low"                  # forced low even though raw conf is high
    assert rec["confidence_score"] == build_data.SKIP_METER_STRONG   # small UX meter, not the raw score
    # the gate code is rendered as a plain-language "why it was set aside" line
    assert rec["gate_note"] == "too little money resting in this market to trade our size safely"


def test_skipped_meter_is_two_or_three_bars():
    by = {u["condition_id"]: u for u in universe()}
    strong = opp("skip"); strong["confidence"] = 0.7    # gated but relatively strong -> 3 bars
    weak = opp("skip"); weak["confidence"] = 0.3        # weak signal -> 2 bars
    assert build_data.opportunity_to_recommendation(strong, by, None)["confidence_score"] == build_data.SKIP_METER_STRONG
    assert build_data.opportunity_to_recommendation(weak, by, None)["confidence_score"] == build_data.SKIP_METER_WEAK


def test_skipped_unknown_reason_falls_back_to_raw():
    by = {u["condition_id"]: u for u in universe()}
    o = opp("skip")
    o["gate"]["reason"] = "some new reason not in the glossary"
    rec = build_data.opportunity_to_recommendation(o, by, None)
    assert rec["gate_note"] == "some new reason not in the glossary"


def test_skipped_without_reason_still_low():
    by = {u["condition_id"]: u for u in universe()}
    rec = build_data.opportunity_to_recommendation(opp("skip"), by, None)   # gate carries no reason
    assert rec["confidence"] == "low"
    assert rec["gate_note"] == "set aside by the risk gate"


def test_strategy_note_explains_the_play():
    by = {u["condition_id"]: u for u in universe()}
    rec = build_data.opportunity_to_recommendation(opp("auto"), by, None)   # strategy risk-free-arb
    assert rec["strategy_note"] == build_data.STRATEGY_NOTES["risk-free-arb"]
    assert "gate_note" not in rec                       # only skipped items carry a gate note


def test_non_skipped_keeps_band_and_meter():
    by = {u["condition_id"]: u for u in universe()}
    for decision in ("auto", "escalate"):
        rec = build_data.opportunity_to_recommendation(opp(decision), by, None)
        assert rec["confidence"] == "high"             # follows the 0.9 raw confidence
        assert rec["confidence_score"] == "0.9"        # meter still populated


# ---- stats come from the FULL universe ----
def test_compute_stats_full_universe():
    st = build_data.compute_stats(universe())
    assert st["active"] == 3
    assert st["volume_24h"] == str(50000 + 900000 + 1000)
    # 0xB has volume_total 5,000,000; others fall back to volume_24h
    assert st["total_volume"] == str(50000 + 5000000 + 1000)


# ---- Markets tab = the most-traded markets in the last 24h (top N by volume, live) ----
def test_markets_limit_constant_is_50():
    assert build_data.MARKETS_LIMIT == 50


def test_markets_ranked_by_24h_volume():
    data = build_data.build_data({"universe": universe(), "opportunities": []})
    conds = [m["condition_id"] for m in data["markets"]]
    assert conds == ["0xB", "0xA", "0xC"]            # 900k > 50k > 1k


def test_markets_capped_at_limit():
    uni = [mkt(f"M{i:03d}", "0.50", str(1000 + i)) for i in range(60)]
    data = build_data.build_data({"universe": uni, "opportunities": []})
    grid = [m["condition_id"] for m in data["markets"]]
    assert len(grid) == 50                            # capped, not 60
    assert "M059" in grid                             # highest 24h volume kept
    assert "M000" not in grid                         # lowest volume dropped past the cap


def test_small_pool_shows_all():
    data = build_data.build_data({"universe": universe(), "opportunities": []})
    assert len(data["markets"]) == 3                  # fewer than the cap -> show all


def test_dead_markets_filtered_from_grid():
    # YES at/below 1% (incl. exactly 0, exactly the 0.01 floor) and missing prices are dead noise
    # -> all dropped even at top volume; only the live 0.40 market survives.
    uni = [mkt("L1", "0.40", "5000"), mkt("D0", "0", "9000"), mkt("D1", "0.005", "8000"),
           mkt("DFLOOR", "0.01", "7000"),                        # exactly the floor -> dropped (strict >)
           {"condition_id": "DNONE", "slug": "dnone", "question": "No price?",
            "volume_24h": "6000", "liquidity": "9000"}]          # missing yes_price -> dropped
    data = build_data.build_data({"universe": uni, "opportunities": []})
    conds = {m["condition_id"] for m in data["markets"]}
    assert conds == {"L1"}


def test_recommendations_not_merged_into_grid():
    # a recommended market that isn't among the hottest is NOT forced into the Markets grid;
    # it still appears in recommendations[].
    hot = [mkt(f"H{i:02d}", "0.50", str(100000 + i)) for i in range(50)]
    low_rec = mkt("0xA", "0.48", "10")                # the rec market, tiny 24h volume
    data = build_data.build_data({"universe": hot + [low_rec], "opportunities": [opp("escalate")]})
    grid = [m["condition_id"] for m in data["markets"]]
    assert "0xA" not in grid                          # not pulled into the grid
    assert len(grid) == 50
    assert data["recommendations"][0]["slug"] == "arb-mkt"   # still recommended


def test_enrichment_merged_into_market():
    enr = {"0xB": {"category": "Politics", "url": "https://polymarket.com/event/big-mkt"}}
    data = build_data.build_data({"universe": universe(), "opportunities": [], "enrichment": enr})
    big = [m for m in data["markets"] if m["condition_id"] == "0xB"][0]
    assert big["category"] == "Politics"
    assert big["url"] == "https://polymarket.com/event/big-mkt"


# ---- account: null unless a wallet is set up (template then shows setup steps) ----
def test_account_absent_is_null():
    data = build_data.build_data({"universe": universe(), "opportunities": []})
    assert data["account"] is None


def test_account_empty_object_coerced_to_null():
    data = build_data.build_data({"universe": universe(), "opportunities": [], "account": {}})
    assert data["account"] is None


def test_account_passed_through_when_set_up():
    acc = {"wallet": {"deposit_wallet": "0x9377"}, "balance": {"cash": "100"}}
    data = build_data.build_data({"universe": universe(), "opportunities": [], "account": acc})
    assert data["account"] == acc


# ---- injection produces exactly one valid DATA block ----
def test_inject_replaces_data_block_once():
    html = TEMPLATE.read_text()
    data = build_data.build_data({"universe": universe(), "opportunities": [opp("auto")]})
    out = build_data.inject(html, data)
    assert out.count("POLYMARKET_DATA_START") == 1
    assert out.count("POLYMARKET_DATA_END") == 1
    assert "generated by build_data.py" in out
    # the injected object parses as JSON
    blob = out.split("const DATA = ", 1)[1].rsplit(";\n/* === POLYMARKET_DATA_END", 1)[0]
    parsed = json.loads(blob)
    assert parsed["recommendations"][0]["question"] == "Arb market?"
