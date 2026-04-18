#!/usr/bin/env python3
"""Cybr Ghost — stealth browser MCP server by CybrFlux.

Exposes a real, human-like browser to AI agents via MCP. Survives bot
detection (Cloudflare, DataDome, Turnstile) by presenting a consistent
browser fingerprint, humanized input, and per-session profile rotation.

Design: the driving LLM (typically Claude Code) is the planner. This
server exposes low-level primitives (navigate/click/type/snapshot/
screenshot) — no autonomous agent loop. Each action returns a fresh page
snapshot so the model can decide the next move.

See NOTICE for third-party attributions.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from camoufox.async_api import AsyncCamoufox
from mcp.server.fastmcp import FastMCP, Image

mcp = FastMCP("cybr-ghost")

# Persistent browser state across tool calls (same MCP session).
_cm: AsyncCamoufox | None = None
_browser: Any = None
_page: Any = None
_lock = asyncio.Lock()

# Env-tunable defaults.
HEADLESS = os.getenv("CYBR_GHOST_HEADLESS", "false").lower() == "true"
HUMANIZE = os.getenv("CYBR_GHOST_HUMANIZE", "true").lower() == "true"
LOCALE = os.getenv("CYBR_GHOST_LOCALE", "en-US")
MAX_ELEMENTS = 150

# JS that tags every visible interactive element with data-ai-ref="N" and
# returns a compact descriptor list. The tags persist so follow-up clicks
# can select by ref even after the snapshot call returned.
_JS_SNAPSHOT = r"""
() => {
    const isVisible = (el) => {
        const r = el.getBoundingClientRect();
        if (r.width < 1 || r.height < 1) return false;
        const s = window.getComputedStyle(el);
        if (s.visibility === 'hidden' || s.display === 'none' || s.opacity === '0') return false;
        if (r.bottom < 0 || r.top > window.innerHeight + 500) return false;
        return true;
    };
    const sel = [
        'a[href]', 'button', 'input:not([type="hidden"])', 'select', 'textarea',
        '[role="button"]', '[role="link"]', '[role="checkbox"]', '[role="menuitem"]',
        '[role="tab"]', '[role="textbox"]', '[role="searchbox"]', '[role="combobox"]',
        '[contenteditable="true"]', '[onclick]', 'summary', 'label'
    ].join(',');
    document.querySelectorAll('[data-ai-ref]').forEach(el => el.removeAttribute('data-ai-ref'));
    const els = [...document.querySelectorAll(sel)].filter(isVisible);
    return els.map((el, i) => {
        el.setAttribute('data-ai-ref', String(i));
        const label = (el.getAttribute('aria-label') || el.getAttribute('title') || '').trim();
        const text = (el.innerText || '').trim().replace(/\s+/g, ' ').slice(0, 140);
        const val = (el.value || '').toString().slice(0, 80);
        const placeholder = (el.getAttribute('placeholder') || '').slice(0, 80);
        return {
            i,
            tag: el.tagName.toLowerCase(),
            type: el.getAttribute('type') || null,
            role: el.getAttribute('role') || null,
            name: el.getAttribute('name') || null,
            id: el.id || null,
            href: el.tagName === 'A' ? (el.getAttribute('href') || null) : null,
            label: label || null,
            text: text || null,
            value: val || null,
            placeholder: placeholder || null,
        };
    });
}
"""


async def _ensure_browser():
    """Launch Camoufox on first use (idempotent)."""
    global _cm, _browser, _page
    async with _lock:
        if _page is not None and not _page.is_closed():
            return _page
        _cm = AsyncCamoufox(
            headless=HEADLESS,
            humanize=HUMANIZE,
            geoip=True,
            locale=LOCALE,
            os=["macos", "windows"],
        )
        _browser = await _cm.__aenter__()
        _page = await _browser.new_page()
        return _page


def _format_element(el: dict) -> str:
    parts = [f"[{el['i']}]", el["tag"]]
    if el["type"]:
        parts.append(f"type={el['type']}")
    if el["role"]:
        parts.append(f"role={el['role']}")
    if el["name"]:
        parts.append(f"name={el['name']}")
    if el["id"]:
        parts.append(f"id={el['id']}")
    label = el["label"] or el["text"] or el["placeholder"]
    if label:
        parts.append(f'"{label}"')
    if el["value"]:
        parts.append(f"(value={el['value']!r})")
    if el["href"]:
        parts.append(f"-> {el['href'][:80]}")
    return " ".join(parts)


async def _snapshot_text(page) -> str:
    try:
        elements = await page.evaluate(_JS_SNAPSHOT)
    except Exception as e:
        return f"Snapshot failed: {e}\nURL: {page.url}"
    lines = [
        f"URL: {page.url}",
        f"Title: {await page.title()}",
        f"Elements: {len(elements)} interactive",
        "",
    ]
    for el in elements[:MAX_ELEMENTS]:
        lines.append(_format_element(el))
    if len(elements) > MAX_ELEMENTS:
        lines.append(f"... ({len(elements) - MAX_ELEMENTS} more not shown — scroll or use eval_js)")
    return "\n".join(lines)


def _ref(index: int) -> str:
    return f'[data-ai-ref="{index}"]'


@mcp.tool()
async def navigate(url: str, wait_until: str = "domcontentloaded") -> str:
    """Navigate to a URL. wait_until: 'domcontentloaded' | 'load' | 'networkidle'.

    Returns a snapshot of interactive elements on the loaded page.
    """
    page = await _ensure_browser()
    await page.goto(url, wait_until=wait_until, timeout=45000)
    return await _snapshot_text(page)


@mcp.tool()
async def snapshot() -> str:
    """Re-snapshot the current page. Use after dynamic content loads or modal opens."""
    page = await _ensure_browser()
    return await _snapshot_text(page)


@mcp.tool()
async def click(index: int) -> str:
    """Click the element with the given snapshot index [N]."""
    page = await _ensure_browser()
    loc = page.locator(_ref(index))
    await loc.scroll_into_view_if_needed(timeout=5000)
    await loc.click(timeout=10000)
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=8000)
    except Exception:
        pass
    await asyncio.sleep(0.4)
    return await _snapshot_text(page)


@mcp.tool()
async def type_text(index: int, text: str, submit: bool = False, clear: bool = True) -> str:
    """Type text into input element [N]. submit=True presses Enter after. clear=True empties field first."""
    page = await _ensure_browser()
    loc = page.locator(_ref(index))
    await loc.scroll_into_view_if_needed(timeout=5000)
    await loc.click(timeout=10000)
    if clear:
        await loc.fill("")
    # Humanlike typing: per-char delay jittered by Camoufox when humanize=True.
    await loc.type(text, delay=35)
    if submit:
        await loc.press("Enter")
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=8000)
        except Exception:
            pass
    return await _snapshot_text(page)


@mcp.tool()
async def press_key(key: str) -> str:
    """Press a keyboard key globally (e.g. 'Enter', 'Escape', 'Tab', 'ArrowDown', 'Control+a')."""
    page = await _ensure_browser()
    await page.keyboard.press(key)
    await asyncio.sleep(0.3)
    return await _snapshot_text(page)


@mcp.tool()
async def scroll(direction: str = "down", amount: int = 600) -> str:
    """Scroll. direction: 'up'|'down'|'top'|'bottom'. amount: pixels for up/down."""
    page = await _ensure_browser()
    if direction == "top":
        await page.evaluate("window.scrollTo({top: 0, behavior: 'instant'})")
    elif direction == "bottom":
        await page.evaluate("window.scrollTo({top: document.body.scrollHeight, behavior: 'instant'})")
    elif direction == "up":
        await page.evaluate(f"window.scrollBy(0, -{amount})")
    else:
        await page.evaluate(f"window.scrollBy(0, {amount})")
    await asyncio.sleep(0.3)
    return await _snapshot_text(page)


@mcp.tool()
async def wait(seconds: float = 2.0) -> str:
    """Wait N seconds (capped at 30) for dynamic content, then return fresh snapshot."""
    await asyncio.sleep(min(max(seconds, 0), 30))
    page = await _ensure_browser()
    return await _snapshot_text(page)


@mcp.tool()
async def wait_for_selector(selector: str, timeout_seconds: float = 15) -> str:
    """Wait for a CSS/XPath selector to appear, then snapshot."""
    page = await _ensure_browser()
    await page.wait_for_selector(selector, timeout=int(timeout_seconds * 1000))
    return await _snapshot_text(page)


@mcp.tool()
async def screenshot(full_page: bool = False) -> Image:
    """Capture a PNG screenshot. Use when snapshot() isn't enough and you need to SEE the page."""
    page = await _ensure_browser()
    data = await page.screenshot(full_page=full_page, type="png")
    return Image(data=data, format="png")


@mcp.tool()
async def get_text() -> str:
    """Get all visible page text (document.body.innerText). Useful for reading articles / extracting content."""
    page = await _ensure_browser()
    return await page.evaluate("() => document.body ? document.body.innerText : ''")


@mcp.tool()
async def get_html(selector: str = "body", max_chars: int = 20000) -> str:
    """Get outer HTML of a selector (default: body). Truncated to max_chars."""
    page = await _ensure_browser()
    html = await page.evaluate(
        "(s) => { const el = document.querySelector(s); return el ? el.outerHTML : ''; }",
        selector,
    )
    if len(html) > max_chars:
        return html[:max_chars] + f"\n... (truncated, {len(html) - max_chars} more chars)"
    return html


@mcp.tool()
async def eval_js(code: str) -> str:
    """Execute arbitrary JS in page context. Escape hatch for things the other tools can't do.

    Example: `document.querySelectorAll('.price').length`
    Return value is stringified.
    """
    page = await _ensure_browser()
    result = await page.evaluate(f"() => {{ return ({code}); }}")
    return str(result)


@mcp.tool()
async def new_tab(url: str | None = None) -> str:
    """Open a new tab (optionally navigate). Subsequent calls target the new tab."""
    global _page
    page = await _ensure_browser()
    _page = await page.context.new_page()
    if url:
        await _page.goto(url, wait_until="domcontentloaded", timeout=45000)
    return await _snapshot_text(_page)


@mcp.tool()
async def list_tabs() -> str:
    """List all open tabs with indices."""
    page = await _ensure_browser()
    pages = page.context.pages
    lines = []
    for i, p in enumerate(pages):
        marker = " (active)" if p is _page else ""
        lines.append(f"[{i}] {p.url} — {await p.title()}{marker}")
    return "\n".join(lines) if lines else "(no tabs)"


@mcp.tool()
async def switch_tab(index: int) -> str:
    """Switch active tab by index from list_tabs."""
    global _page
    page = await _ensure_browser()
    pages = page.context.pages
    if not 0 <= index < len(pages):
        return f"Invalid tab index {index}. {len(pages)} tabs open."
    _page = pages[index]
    await _page.bring_to_front()
    return await _snapshot_text(_page)


@mcp.tool()
async def close_browser() -> str:
    """Close the browser and release resources. Next call re-launches."""
    global _cm, _browser, _page
    async with _lock:
        if _cm is not None:
            try:
                await _cm.__aexit__(None, None, None)
            except Exception as e:
                return f"Close error (state cleared anyway): {e}"
            finally:
                _cm = _browser = _page = None
        return "Browser closed."


if __name__ == "__main__":
    mcp.run()
