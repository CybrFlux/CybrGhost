# How Cybr Ghost Beats Bot Detection

A short, honest accounting of what works, what doesn't, and why.

## The three things bot detectors look at

1. **Client fingerprint** — automated flags, plugin list, WebGL
   vendor/renderer, canvas hash, fonts, screen properties, `navigator.*`
   values, timezone, locale.
2. **Behavioral signals** — mouse path linearity, keystroke cadence,
   click precision, scroll easing, dwell time.
3. **Network signals** — TLS fingerprint (JA3/JA4), HTTP/2 frame order,
   IP reputation, header ordering.

Cybr Ghost addresses (1) and (2). (3) is your proxy's problem.

## Fingerprint — what we clean up

Stock browser-automation toolchains leak bot-indicators in roughly eight
places that popular detectors (Cloudflare, DataDome, Akamai Bot Manager)
check:

| Leak | Stock automation | Cybr Ghost |
|---|---|---|
| `navigator.webdriver` | `true` | absent |
| `navigator.plugins.length` | `0` | `5+` |
| `PluginArray` prototype | missing | present |
| `HeadlessChrome` in UA | yes | no — real Firefox UA |
| WebGL vendor | `Google SwiftShader` | real GPU (rotated per session) |
| Canvas/audio fingerprint noise | missing | applied |
| Chrome runtime object | empty | genuinely absent (Firefox) |
| CDP runtime artifacts | detectable | patched at C++ level |

The patches are applied to the browser **at the source C++ level**, not
with JS injection. JS-patch approaches (`puppeteer-extra-stealth` and
friends) lose an arms race against detectors that inspect
`Function.prototype.toString` for patched native functions. Native-level
values look native because they are native.

## Per-session fingerprint rotation

On each launch, Cybr Ghost rolls a new consistent profile: OS, CPU count,
screen size, font list, WebGL vendor/renderer, timezone. The set is
internally consistent — a Mac profile doesn't get an NVIDIA GPU.

The test suite confirms this. Across three runs we observed:

- Run 1: Mac + Intel HD Graphics 400
- Run 2: Windows + NVIDIA GeForce GTX 980
- Run 3: Windows + AMD Radeon HD 3200

A detector tracking fingerprint across a session doesn't see the same
"bot" twice.

## Humanized input

With `CYBR_GHOST_HUMANIZE=true` (default), every mouse and keyboard
interaction is injected with:

- Bezier-curve mouse paths with per-segment velocity variation.
- Pre-click dwell and micro-jitter at the target.
- Per-character typing delay (`type_text` uses 35ms base + jitter).

Linear mouse paths are the #1 behavioral tell. Humanize breaks that.

## What it does NOT solve

- **Interactive CAPTCHAs** — reCAPTCHA v2 image challenges, hCaptcha.
  Cybr Ghost can click the checkbox; if the detector escalates to a
  visual challenge, you need an external solver (2captcha, CapSolver).
- **IP reputation** — if your datacenter IP is on a block list, no
  browser fingerprint saves you. Use residential proxies for hard
  targets.
- **Account-based detection** — a fresh browser profile with a 10-year-
  old account and no history is suspicious regardless of fingerprint.
- **TLS fingerprint** — the TLS stack is Firefox's real one, so it
  matches the declared UA. A mismatched proxy can ruin this.

## Test results

From `tests/test_stealth.py` (current, green):

- **bot.sannysoft.com** — 5/5 critical checks pass:
  `WebDriver (New)`, `WebDriver Advanced`, `PluginArray type`,
  plugin count > 0, real WebGL vendor.
- **google.com/search** — full search results render, no "unusual
  traffic" block, snapshot captures 40+ interactive elements cleanly.
- **nowsecure.nl** (Cloudflare Turnstile) — challenge auto-solved via
  iframe-checkbox click, real site content reached.

## Responsible use

This tool exists because AI agents need real web access. Use it for
automation against services you own, APIs without proper public
interfaces, and legal scraping. Respect robots.txt, rate limits, and
terms of service. Don't use it to harass, defraud, or ddos.
