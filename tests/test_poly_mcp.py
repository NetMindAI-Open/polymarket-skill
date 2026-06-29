import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "assets" / "poly-mcp.sh"


def test_usage_without_tool():
    r = subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True)
    assert r.returncode == 1
    assert "usage" in (r.stdout + r.stderr).lower()


def test_errors_without_token(tmp_path):
    empty = tmp_path / "empty.json"
    empty.write_text("{}")
    env = {**os.environ, "POLY_MCP_CONFIG": str(empty), "POLY_MCP_URL": "", "POLY_MCP_AUTH": ""}
    r = subprocess.run(
        ["bash", str(SCRIPT), "screen_markets", "{}"],
        env=env, capture_output=True, text=True,
    )
    assert r.returncode == 1
    assert "no polymarket mcp token" in (r.stdout + r.stderr).lower()
