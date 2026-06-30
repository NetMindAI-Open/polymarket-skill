# Calling the Polymarket MCP

The polymarket MCP server (`polymarket-data`) provides read-only market analytics:
`list_events`, `list_markets`, `get_market`, `search_markets`, `screen_markets`,
`get_price_history`, `get_trades`, `get_market_stats`, `get_order_book`, `get_order_book_depth`.

## Use the transport helper

Native `mcp__polymarket__*` tool calls may be blocked by the ECC plugin's
`mcp-health-check.js` hook (a false positive — see below). Always reach the server
through the helper, which works regardless of the hook:

    assets/poly-mcp.sh <tool_name> '<json_args>'
    # e.g.
    assets/poly-mcp.sh screen_markets '{"sort_by":"volume_spike","interval":"24h","min_liquidity":20000,"min_volume_24h":100000,"limit":10}'
    assets/poly-mcp.sh get_order_book_depth '{"token_id":"123...","notional":100}'

The helper reads the URL + bearer token from `~/.claude.json` (`mcpServers.polymarket`)
and never prints the token. It prints the tool's JSON result to stdout, or
`{"error":…}` with exit 1 on failure.

## Speed: never loop single calls — go native, or batch

Every `poly-mcp.sh <tool>` invocation pays the **full MCP handshake** (`initialize`
→ `notifications/initialized` → `tools/call`) — ~5s of round-trips, almost all of it
the handshake, not the query. A loop of N single calls pays it N times (≈ N×5s), which
is what makes enrichment crawl. In rough order of preference:

1. **Native `mcp__polymarket__*` tools** — the client holds one persistent session, so
   there is **no per-call handshake**; calls return in well under a second. Use these
   whenever they're reachable (they usually are; the health-check false-positive below
   rarely actually blocks them). This is the fastest path and the default for the
   orchestrator's own scout + enrichment pulls.
2. **`poly-mcp.sh --batch`** — one handshake amortized across many calls. Feed NDJSON on
   **stdin**, one object per line, read NDJSON on stdout:

       printf '%s\n' \
         '{"id":"spain:depth","tool":"get_order_book_depth","args":{"token_id":"4394…"}}' \
         '{"id":"spain:stats","tool":"get_market_stats","args":{"condition_id":"0x79…","interval":"24h"}}' \
       | assets/poly-mcp.sh --batch
       # -> {"id":"spain:depth","ok":true,"result":{…}}
       #    {"id":"spain:stats","ok":true,"result":{…}}

   `id` (defaults to line index) lets you join results back to markets; `result` is the
   tool's payload parsed as JSON. A per-call failure yields `{"id":…,"ok":false,"error":…}`
   and does **not** abort the batch. Use this when native tools are unavailable (e.g.
   inside a shell-only sub-agent), instead of a per-call loop.

   Even within `--batch`, calls run **sequentially** on the one session and each tool query
   still costs ~2s of server-side latency, so a 48-call batch ≈ 110s. To also hide that
   latency, **shard the calls across ~4 parallel `--batch` invocations** (each pays its own
   one-time handshake, but the queries overlap): measured ~30s for the same 48 calls vs ~110s
   single-batch. The MCP tolerates this concurrency; ~4 shards is a good default.
3. **`poly-mcp.sh <tool> '<json>'`** — single call, full handshake. Fine for one-off reads;
   never put it in a loop.

For event metadata from the **Gamma** REST API, batch too: `…/markets?condition_ids=a&condition_ids=b&…`
returns all markets in one request. Use `curl` (serial) — firing many concurrent Gamma
requests gets HTTP 429 rate-limited.

## Why native calls 406 (and the optional fix)

The MCP endpoint is healthy. The health-check hook probes it with
`Accept: application/json` only; the server correctly requires
`Accept: application/json, text/event-stream` and returns HTTP 406, so the hook
wrongly marks the server unavailable and blocks the tools.

Optional fix for interactive native calls: whitelist `polymarket` in the
health-check hook (or correct its `Accept` header). Not required — the helper is
the supported path for this skill.
