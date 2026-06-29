import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "assets" / "risk_gate.py"
FIXTURE = Path(__file__).parent / "fixtures" / "opportunity.valid.json"


def run(args, stdin):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        input=stdin, capture_output=True, text=True,
    )


def test_cli_decide_auto():
    r = run(["decide", "--run-total", "0"], FIXTURE.read_text())
    assert r.returncode == 0
    assert json.loads(r.stdout)["decision"] == "auto"


def test_cli_decide_over_cap_skips():
    opp = json.loads(FIXTURE.read_text())
    opp["proposed_action"]["size_usd"] = 999
    r = run(["decide", "--run-total", "0"], json.dumps(opp))
    assert json.loads(r.stdout)["decision"] == "skip"


def test_cli_validate_rejects_bad_object():
    r = run(["validate"], json.dumps({"strategy": "momentum"}))
    assert r.returncode == 1
    assert json.loads(r.stdout)["errors"]
