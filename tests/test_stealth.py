"""CybrGhost validation suite.

Three live tests with hard assertions:
  1. Sannysoft fingerprint — proves WebDriver / plugin / WebGL stealth.
  2. Google search — proves real-world interactivity + no CAPTCHA block.
  3. Cloudflare Turnstile (nowsecure.nl) — proves challenge bypass.

Exits non-zero if any assertion fails. Runs headless for CI; flip
CYBR_GHOST_HEADLESS=false locally to watch it.
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import sys
import traceback

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("CYBR_GHOST_HEADLESS", "true")
os.environ.setdefault("CYBR_GHOST_HUMANIZE", "true")

import server  # noqa: E402

SHOTS = pathlib.Path("/tmp/CybrGhost-test")
SHOTS.mkdir(exist_ok=True)

RESULTS: list[tuple[str, bool, str]] = []


def log(label: str, ok: bool, msg: str) -> None:
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {label}: {msg}")
    RESULTS.append((label, ok, msg))


async def test_sannysoft(page) -> None:
    print("\n=== TEST 1: Sannysoft fingerprint ===")
    await page.goto("https://bot.sannysoft.com/", wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(4)
    await page.screenshot(path=str(SHOTS / "01-sannysoft.png"), full_page=True)

    table = await page.evaluate("""
        () => {
            const norm = (s) => s.trim().replace(/\\s+/g, ' ');
            const rows = [...document.querySelectorAll('table tr')];
            const obj = {};
            rows.forEach(r => {
                const cells = [...r.querySelectorAll('td')].map(c => norm(c.innerText));
                if (cells.length >= 2) obj[cells[0]] = cells.slice(1).join(' | ');
            });
            return obj;
        }
    """)

    # Firefox-stealth critical checks. Chrome-specific "failures" are expected
    # for a real Firefox browser (no window.chrome object).
    critical = {
        "WebDriver (New)": "passed",
        "WebDriver Advanced": "passed",
        "Plugins is of type PluginArray": "passed",
    }
    for key, expected in critical.items():
        actual = table.get(key, "MISSING")
        log(f"sannysoft/{key}", expected.lower() in actual.lower(), f"got {actual!r}")

    # Stock headless reports 0 plugins — a real browser reports >= 1.
    plugins_raw = table.get("Plugins Length (Old)", "0")
    count = int("".join(c for c in plugins_raw if c.isdigit()) or "0")
    log("sannysoft/plugin_count", count > 0, f"{count} plugins")

    # WebGL must report real hardware, never SwiftShader (headless giveaway).
    vendor = table.get("WebGL Vendor", "")
    renderer = table.get("WebGL Renderer", "")
    log(
        "sannysoft/webgl",
        vendor != "" and "swiftshader" not in (vendor + renderer).lower(),
        f"{vendor} / {renderer}",
    )


async def test_google(page) -> None:
    print("\n=== TEST 2: Google search ===")
    await page.goto(
        "https://www.google.com/search?q=claude+anthropic",
        wait_until="domcontentloaded",
        timeout=30000,
    )
    await asyncio.sleep(2)
    await page.screenshot(path=str(SHOTS / "02-google.png"), full_page=False)

    title = await page.title()
    body = await page.evaluate("() => document.body.innerText.slice(0, 2000).toLowerCase()")

    log("google/title_has_query", "claude" in title.lower(), f"title={title!r}")
    log(
        "google/no_captcha",
        "unusual traffic" not in body and "sorry" not in body[:200],
        "no block page detected",
    )
    snap = await server._snapshot_text(page)
    el_line = snap.splitlines()[2] if len(snap.splitlines()) > 2 else ""
    log(
        "google/snapshot_has_elements",
        "Elements:" in el_line and not el_line.endswith("0 interactive"),
        el_line,
    )


async def click_turnstile(page) -> bool:
    """Hunt for the Turnstile checkbox iframe and click it. Humanize handles motion."""
    for _ in range(20):
        for frame in page.frames:
            if "challenges.cloudflare.com" not in frame.url:
                continue
            try:
                cb = await frame.wait_for_selector(
                    'input[type="checkbox"]', timeout=1000, state="attached"
                )
                if cb:
                    await cb.click(timeout=3000)
                    return True
            except Exception:
                continue
        await asyncio.sleep(0.5)
    return False


async def test_cloudflare(page) -> None:
    print("\n=== TEST 3: Cloudflare Turnstile (nowsecure.nl) ===")
    await page.goto("https://nowsecure.nl/", wait_until="domcontentloaded", timeout=45000)
    await asyncio.sleep(3)

    title = await page.title()
    if "just a moment" in title.lower() or "attention" in title.lower():
        clicked = await click_turnstile(page)
        log("cloudflare/turnstile_click", clicked, "clicked" if clicked else "no widget")
        for _ in range(15):
            await asyncio.sleep(1)
            title = await page.title()
            if "just a moment" not in title.lower() and "attention" not in title.lower():
                break

    await page.screenshot(path=str(SHOTS / "03-cloudflare.png"), full_page=False)
    final_title = await page.title()
    body = await page.evaluate("() => document.body.innerText")
    body_lower = body.lower()
    challenge_markers = ("just a moment", "attention required", "cloudflare", "verify")
    is_challenge = any(m in final_title.lower() for m in challenge_markers)
    has_challenge_body = "verify you are human" in body_lower[:500]
    passed = not is_challenge and not has_challenge_body and len(body.strip()) > 0
    log("cloudflare/challenge_passed", passed, f"title={final_title!r}, body={body.strip()[:100]!r}")


async def main() -> int:
    try:
        page = await server._ensure_browser()
        await test_sannysoft(page)
        await test_google(page)
        await test_cloudflare(page)
    except Exception:
        traceback.print_exc()
        return 1
    finally:
        if server._cm is not None:
            await server._cm.__aexit__(None, None, None)

    print("\n" + "=" * 60)
    total = len(RESULTS)
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"RESULTS: {passed}/{total} passed")
    for label, ok, msg in RESULTS:
        print(f"  {'PASS' if ok else 'FAIL'}  {label}")
    print("=" * 60)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
