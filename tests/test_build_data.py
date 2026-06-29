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


# ---- confidence banding matches the risk gate thresholds ----
def test_confidence_band():
    assert build_data.confidence_band(0.9) == "high"
    assert build_data.confidence_band(0.75) == "high"
    assert build_data.confidence_band(0.6) == "medium"
    assert build_data.confidence_band(0.4) == "low"


# ---- opportunity -> recommendation mapping ----
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


# ---- stats come from the FULL universe ----
def test_compute_stats_full_universe():
    st = build_data.compute_stats(universe())
    assert st["active"] == 3
    assert st["volume_24h"] == str(50000 + 900000 + 1000)
    # 0xB has volume_total 5,000,000; others fall back to volume_24h
    assert st["total_volume"] == str(50000 + 5000000 + 1000)


# ---- curation: recommended markets always included; subset, not whole universe ----
def test_curation_includes_recommended_and_top_n():
    payload = {"universe": universe(), "opportunities": [opp("auto")], "top_n": 1,
               "enrichment": {"0xA": {"url": "https://polymarket.com/event/arb-mkt",
                                      "category": "Politics", "candles": [], "depth": {"bids": [], "asks": []}}}}
    data = build_data.build_data(payload)
    conds = [m["condition_id"] for m in data["markets"]]
    assert "0xA" in conds                       # recommended market always present
    assert "0xB" in conds                       # highest-volume top_n
    enriched = [m for m in data["markets"] if m["condition_id"] == "0xA"][0]
    assert enriched["category"] == "Politics"   # enrichment merged
    assert data["meta"]["stats"]["active"] == 3           # stats reflect full universe, not the subset
    assert data["recommendations"][0]["status"] == "executed"


# ---- trending: 24h-hot markets merged into the grid, deduped + tagged ----
def trending():
    return [
        {"condition_id": "0xHOT", "slug": "hot-mkt", "question": "Hot market?", "yes_price": "0.55",
         "volume_24h": "3000000", "liquidity": "120000", "token_id_yes": "411", "token_id_no": "412"},
        {"condition_id": "0xB", "slug": "big-mkt", "question": "Big market?", "yes_price": "0.30",
         "volume_24h": "900000", "token_id_yes": "211", "token_id_no": "212"},  # also scouted -> dedup
    ]


def test_trending_markets_merged_and_tagged():
    payload = {"universe": universe(), "opportunities": [opp("auto")], "top_n": 1,
               "trending": trending(), "trending_n": 5}
    data = build_data.build_data(payload)
    by = {m["condition_id"]: m for m in data["markets"]}
    # the hot-only market is added and tagged (no real category -> chip/tag for free)
    assert "0xHOT" in by
    assert by["0xHOT"]["trending"] is True
    assert by["0xHOT"]["category"] == "🔥 Trending"
    # a market that is BOTH scouted and trending is flagged, not duplicated
    assert [m["condition_id"] for m in data["markets"]].count("0xB") == 1
    assert by["0xB"]["trending"] is True


def test_trending_respects_trending_n():
    payload = {"universe": universe(), "opportunities": [], "top_n": 0,
               "trending": trending(), "trending_n": 1}
    data = build_data.build_data(payload)
    # only the single highest-volume trending market (0xHOT) is merged
    assert any(m["condition_id"] == "0xHOT" for m in data["markets"])


def test_trending_absent_is_noop():
    data = build_data.build_data({"universe": universe(), "opportunities": [opp("auto")], "top_n": 1})
    assert all("trending" not in m for m in data["markets"])


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
