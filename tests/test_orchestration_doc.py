from pathlib import Path

DOC = Path(__file__).parent.parent / "reference" / "orchestration.md"


def test_orchestration_covers_flow_and_tools():
    text = DOC.read_text()
    for needle in [
        "poly-mcp.sh", "risk_gate.py", "Scout", "Fan-out",
        "auto", "escalate", "skip", "--dry-run", "--yes",
    ]:
        assert needle in text, f"orchestration.md missing: {needle}"
