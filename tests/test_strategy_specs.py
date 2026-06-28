from pathlib import Path

import pytest

STRAT_DIR = Path(__file__).parent.parent / "reference" / "strategies"
NAMES = ["momentum", "mean-reversion", "multi-outcome-arb", "spread-capture", "risk-free-arb", "smart-money"]
SECTIONS = ["**Goal:**", "## Data to pull", "## Signal logic", "## Disqualifiers", "## Confidence rubric", "## Output mapping"]


@pytest.mark.parametrize("name", NAMES)
def test_strategy_spec_complete(name):
    path = STRAT_DIR / f"{name}.md"
    assert path.exists(), f"missing {path}"
    text = path.read_text()
    for section in SECTIONS:
        assert section in text, f"{name}.md missing section: {section}"
