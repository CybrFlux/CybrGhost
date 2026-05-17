# Changelog

All notable changes to CybrGhost are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-04-18

### Added
- Initial release by CybrFlux.
- MCP stdio server exposing a stealth browser to AI agents.
- 16 browser tools:
  - **Navigation:** `navigate`, `new_tab`, `list_tabs`, `switch_tab`
  - **Inspection:** `snapshot`, `screenshot`, `get_text`, `get_html`
  - **Actions:** `click`, `type_text`, `press_key`, `scroll`
  - **Waiting:** `wait`, `wait_for_selector`
  - **Escape hatch:** `eval_js`, `close_browser`
- Accessibility snapshot system with numbered element references (`[N] tag …`).
- Environment-variable config: `CYBR_GHOST_HEADLESS`, `CYBR_GHOST_HUMANIZE`, `CYBR_GHOST_LOCALE`.
- Per-session fingerprint rotation (WebGL vendor/renderer, OS, locale).
- Humanized input — realistic mouse movement and per-character typing delay.
- Validation suite with 9 assertions covering fingerprint checks,
  Google search interaction, and Cloudflare Turnstile challenge bypass.

### Known limitations
- Interactive CAPTCHAs (reCAPTCHA v2 image challenges, hCaptcha) still require an
  external solver — not bundled in v0.1.
- macOS tested; Linux should work but untested in CI.
- Single active tab model: `switch_tab` designates the active target for
  subsequent tool calls.
