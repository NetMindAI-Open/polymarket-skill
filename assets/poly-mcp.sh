#!/usr/bin/env bash
# Thin MCP-over-HTTP transport for the polymarket MCP server.
# Usage: poly-mcp.sh <tool_name> [json_args]
# Prints the tool's JSON text result to stdout. Never prints the bearer token.
set -euo pipefail

TOOL="${1:-}"
ARGS="${2:-{}}"
CONFIG="${POLY_MCP_CONFIG:-$HOME/.claude.json}"

if [ -z "$TOOL" ]; then
  echo '{"error":"usage: poly-mcp.sh <tool_name> [json_args]"}' >&2
  exit 1
fi

URL="${POLY_MCP_URL:-}"
AUTH="${POLY_MCP_AUTH:-}"
if [ -z "$URL" ] || [ -z "$AUTH" ]; then
  read -r URL AUTH < <(python3 - "$CONFIG" <<'PY'
import json, sys
try:
    cfg = json.load(open(sys.argv[1]))
    e = cfg["mcpServers"]["polymarket"]
    print(e["url"], e["headers"]["Authorization"])
except Exception:
    print("", "")
PY
)
fi

if [ -z "$URL" ] || [ -z "$AUTH" ]; then
  echo '{"error":"no polymarket MCP token/url found in config"}' >&2
  exit 1
fi

ACC="Accept: application/json, text/event-stream"
CT="Content-Type: application/json"
AUTHH="Authorization: $AUTH"

INIT='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"poly-mcp.sh","version":"1"}}}'
SID=$(curl -fsS -D - -o /dev/null -X POST "$URL" -H "$AUTHH" -H "$CT" -H "$ACC" -d "$INIT" \
  | awk -F': ' 'tolower($1)=="mcp-session-id"{print $2}' | tr -d '\r')
if [ -z "$SID" ]; then
  echo '{"error":"MCP initialize failed (no session id)"}' >&2
  exit 1
fi
SIDH="Mcp-Session-Id: $SID"

curl -fsS -o /dev/null -X POST "$URL" -H "$AUTHH" -H "$CT" -H "$ACC" -H "$SIDH" \
  -d '{"jsonrpc":"2.0","method":"notifications/initialized"}'

REQ=$(python3 - "$TOOL" "$ARGS" <<'PY'
import json, sys
print(json.dumps({"jsonrpc":"2.0","id":2,"method":"tools/call",
  "params":{"name":sys.argv[1],"arguments":json.loads(sys.argv[2])}}))
PY
)
curl -fsS -X POST "$URL" -H "$AUTHH" -H "$CT" -H "$ACC" -H "$SIDH" -d "$REQ" \
  | sed -n 's/^data: //p' \
  | python3 - <<'PY'
import json, sys
raw = sys.stdin.read().strip()
if not raw:
    print('{"error":"empty MCP response"}'); sys.exit(1)
d = json.loads(raw.splitlines()[-1])
if "error" in d:
    print(json.dumps({"error": d["error"]})); sys.exit(1)
for c in d.get("result", {}).get("content", []):
    if c.get("type") == "text":
        print(c["text"])
PY
