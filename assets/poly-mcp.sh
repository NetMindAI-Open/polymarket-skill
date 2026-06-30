#!/usr/bin/env bash
# MCP-over-HTTP transport for the polymarket MCP server.
#
# Two modes (both reuse ONE session + ONE keep-alive TCP connection, so the
# initialize handshake is paid once, not per call):
#
#   Single:  poly-mcp.sh <tool_name> [json_args]
#            -> prints the tool's JSON text result to stdout (exit 1 on failure).
#
#   Batch:   poly-mcp.sh --batch < calls.ndjson
#            stdin = one JSON object per line: {"id"?: "...", "tool": "...", "args"?: {...}}
#            stdout = one JSON object per line: {"id": "...", "ok": true, "result": <parsed>}
#                     or {"id": "...", "ok": false, "error": "..."}
#            `id` defaults to the line index. `result` is the tool's text parsed
#            as JSON when possible, else the raw string. Per-call failures do not
#            abort the batch; a failed handshake exits 1.
#
# Prefer --batch (or the native mcp__polymarket__* tools) over a loop of single
# calls: a single call still costs the full handshake (~5s of round-trips),
# whereas --batch amortizes it across every line. Never prints the bearer token.
set -euo pipefail

# The program is written to a temp file (not piped on stdin) so --batch mode can
# read NDJSON from stdin.
_POLY_MCP_PY="$(mktemp "${TMPDIR:-/tmp}/poly-mcp.XXXXXX")"
trap 'rm -f "$_POLY_MCP_PY"' EXIT
cat >"$_POLY_MCP_PY" <<'PY'
import json, os, sys
import http.client
from urllib.parse import urlparse

def resolve_endpoint():
    url = os.environ.get("POLY_MCP_URL", "")
    auth = os.environ.get("POLY_MCP_AUTH", "")
    if url and auth:
        return url, auth
    cfg_path = os.environ.get("POLY_MCP_CONFIG") or os.path.expanduser("~/.claude.json")
    try:
        cfg = json.load(open(cfg_path))
        e = cfg["mcpServers"]["polymarket"]
        return e["url"], e["headers"]["Authorization"]
    except Exception:
        return "", ""

def die(msg, code=1):
    print(json.dumps({"error": msg}))
    sys.exit(code)

URL, AUTH = resolve_endpoint()
if not URL or not AUTH:
    die("no polymarket MCP token/url found in config")

u = urlparse(URL)
is_https = u.scheme == "https"
host = u.hostname
port = u.port or (443 if is_https else 80)
path = u.path or "/"
if u.query:
    path += "?" + u.query

ACCEPT = "application/json, text/event-stream"
BASE_HEADERS = {
    "Authorization": AUTH,
    "Content-Type": "application/json",
    "Accept": ACCEPT,
}

conn = (http.client.HTTPSConnection if is_https else http.client.HTTPConnection)(host, port, timeout=30)

def post(body, extra_headers=None, want_headers=False):
    headers = dict(BASE_HEADERS)
    if extra_headers:
        headers.update(extra_headers)
    conn.request("POST", path, body=body, headers=headers)
    resp = conn.getresponse()
    raw = resp.read().decode("utf-8", "replace")
    hdrs = {k.lower(): v for k, v in resp.getheaders()}
    return (resp.status, raw, hdrs) if want_headers else (resp.status, raw)

def parse_sse_result(raw):
    # MCP HTTP transport replies as SSE: lines of "data: {json}". Take the last.
    data_lines = [ln[6:] for ln in raw.splitlines() if ln.startswith("data: ")]
    if not data_lines:
        # Some deployments reply with a bare JSON body.
        raw = raw.strip()
        if raw.startswith("{"):
            data_lines = [raw]
        else:
            return None, "empty MCP response"
    try:
        d = json.loads(data_lines[-1])
    except Exception as ex:
        return None, "unparseable MCP response: %s" % ex
    if "error" in d:
        return None, json.dumps(d["error"])
    texts = [c.get("text") for c in d.get("result", {}).get("content", []) if c.get("type") == "text"]
    return ("\n".join(t for t in texts if t is not None), None)

# --- handshake (once) ---
INIT = json.dumps({
    "jsonrpc": "2.0", "id": 1, "method": "initialize",
    "params": {"protocolVersion": "2025-06-18", "capabilities": {},
               "clientInfo": {"name": "poly-mcp.sh", "version": "2"}},
})
try:
    status, raw, hdrs = post(INIT, want_headers=True)
except Exception as ex:
    die("MCP connection failed: %s" % ex)
sid = hdrs.get("mcp-session-id")
if not sid:
    die("MCP initialize failed (no session id; HTTP %s)" % status)
SIDH = {"Mcp-Session-Id": sid}
try:
    post(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}), SIDH)
except Exception:
    pass  # notification is best-effort

_next_id = [1]
def call_tool(tool, args):
    _next_id[0] += 1
    req = json.dumps({"jsonrpc": "2.0", "id": _next_id[0], "method": "tools/call",
                      "params": {"name": tool, "arguments": args or {}}})
    status, raw = post(req, SIDH)
    return parse_sse_result(raw)

argv = sys.argv[1:]
if argv and argv[0] == "--batch":
    for idx, line in enumerate(sys.stdin):
        line = line.strip()
        if not line:
            continue
        try:
            spec = json.loads(line)
            cid = spec.get("id", idx)
            tool = spec["tool"]
            args = spec.get("args", {})
        except Exception as ex:
            print(json.dumps({"id": idx, "ok": False, "error": "bad batch line: %s" % ex}))
            continue
        text, err = call_tool(tool, args)
        if err is not None:
            print(json.dumps({"id": cid, "ok": False, "error": err}))
            continue
        try:
            result = json.loads(text)
        except Exception:
            result = text
        print(json.dumps({"id": cid, "ok": True, "result": result}))
    sys.exit(0)

# --- single-call mode (back-compat) ---
if not argv:
    die("usage: poly-mcp.sh <tool_name> [json_args]   |   poly-mcp.sh --batch < calls.ndjson")
tool = argv[0]
try:
    args = json.loads(argv[1]) if len(argv) > 1 and argv[1] else {}
except Exception as ex:
    die("invalid json args: %s" % ex)
text, err = call_tool(tool, args)
if err is not None:
    die(err)
print(text)
PY

python3 "$_POLY_MCP_PY" "$@"
