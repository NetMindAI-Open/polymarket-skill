from pathlib import Path

ROOT = Path(__file__).parent.parent


def test_skill_has_scanning_section():
    text = (ROOT / "SKILL.md").read_text()
    assert "Opportunity scanning" in text
    assert "reference/orchestration.md" in text
    assert "scan" in text.lower()


def test_readme_mentions_scanning():
    text = (ROOT / "README.md").read_text()
    assert "scan" in text.lower()
