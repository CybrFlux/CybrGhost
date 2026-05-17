# Architecture

CybrGhost is three layers. Each can be swapped independently.

```
┌─────────────────────────────────────────────────────────────┐
│  Driver  (Claude Code / any MCP client)                     │
│  ─ The planner. Decides what to click/type based on the     │
│    accessibility snapshot. Not part of this repo.           │
└──────────────────────────┬──────────────────────────────────┘
                           │ MCP over stdio (JSON-RPC 2.0)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  CybrGhost MCP server  (server.py)                        │
│  ─ FastMCP registers 16 tools.                              │
│  ─ Each tool: grabs the active page → performs the          │
│    primitive → runs the snapshot JS → returns text.         │
│  ─ Holds one browser instance per MCP session.              │
│  ─ Humanized input, per-session fingerprint rotation,       │
│    geoip locale, OS spoofing policy.                        │
└──────────────────────────┬──────────────────────────────────┘
                           │ browser automation protocol
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  Stealth browser runtime                                    │
│  ─ Real Firefox engine with anti-detect patches applied     │
│    at the C++ level.                                        │
│  ─ Clean fingerprint, real plugin list, real WebGL values.  │
└─────────────────────────────────────────────────────────────┘
```

(See `NOTICE` for third-party components in the stealth runtime layer.)

## Why a thin server?

Most browser-automation agents embed an LLM loop inside the automation tool:
page → LLM → action → page → LLM … The LLM inside the tool calls your chosen
API with your API key. That's fine when automation runs headless in CI.

When the driver is **already an LLM** — as with Claude Code talking to this
MCP server — that inner loop is redundant. You'd pay for two Claude calls
per action: one driving the tool, one inside it deciding what to click.

CybrGhost strips that out. The MCP client (Claude) is the planner.
The server exposes primitives, not policies.

## Snapshot format

Every action returns a text block:

```
URL: https://example.com/page
Title: Example page
Elements: 39 interactive

[0]  a href="/home" "Home"
[1]  input type=email name=email placeholder="Your email"
[2]  button type=submit "Sign in"
...
```

The snapshot function:

1. Runs JS in the page that walks the DOM for interactive selectors
   (`a[href]`, `button`, `input`, `[role="button"]`, `[onclick]`, …).
2. Filters to elements that are actually visible (CSS + bounding-box
   intersect with viewport).
3. Tags each matched element with `data-ai-ref="N"` as a stable handle.
4. Returns a compact descriptor per element: tag, type, role, name, id,
   href, text/label/placeholder.

The `data-ai-ref` attribute persists until the next snapshot, so follow-up
`click(5)` / `type_text(3, "...")` calls just look up
`[data-ai-ref="N"]` — no fragile selectors.

## Session lifecycle

```
MCP start
  ↓
First tool call → _ensure_browser() → launch stealth runtime
  ↓
All subsequent calls reuse the same browser + page
  ↓
close_browser() → tear down (next call re-launches)
  ↓
MCP stop → runtime exits
```

One browser per MCP session. `new_tab` creates additional pages inside
the same browser context (cookies shared across tabs).

## Error handling philosophy

- **Never swallow the exception silently.** Tool calls that fail return the
  exception message as the tool result — Claude can see it and react.
- **Keep state consistent on failure.** A `click` that times out leaves
  the browser open; the next `snapshot()` still works.
- **Short, explicit timeouts.** 10s for clicks, 45s for navigation,
  15s for `wait_for_selector`.

## Concurrency

`_ensure_browser()` is guarded by `asyncio.Lock` so simultaneous tool
calls don't race to launch two browsers. Within a launched session, each
tool call runs sequentially on the event loop — no cross-tool
coordination needed.

## Extensibility

Adding a tool is three things:

1. An `@mcp.tool()` async function in `server.py`.
2. A docstring (becomes the tool description the LLM sees).
3. A test case in `tests/test_stealth.py`.

Keep tools atomic. "Log into the site and fetch orders" is not a tool —
that's a planner job. "Click element 5" and "type text into element 3"
are tools.
