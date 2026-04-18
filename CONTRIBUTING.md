# Contributing to Cybr Ghost

Thanks for your interest. A few ground rules to keep the project small, sharp,
and useful.

## Scope

Cybr Ghost is deliberately a **thin** MCP server. The intelligence lives in
whatever LLM is driving (usually Claude). Tools are added only when existing
primitives genuinely can't express the action.

**In scope:** browser primitives, stealth tuning, fingerprint diagnostics,
cross-platform reliability, better snapshots, tests.

**Out of scope:** agent/planner loops (use the driving LLM), workflow
orchestration, hosted services (run it yourself).

## Development setup

```bash
git clone https://github.com/M4ST3R-C0NTR0L/cybr-ghost
cd cybr-ghost
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m camoufox fetch  # one-time browser runtime download
```

## Running tests

```bash
.venv/bin/python tests/test_stealth.py
```

The full suite opens real pages (bot.sannysoft.com, google.com, nowsecure.nl).
Expect ~60 seconds of runtime end-to-end.

## Pull requests

- One concern per PR.
- Keep diffs small — under 400 lines is ideal.
- New tools require: a test case, a README entry, and a real-world example.
- Don't add dependencies without a strong reason — every added dep increases
  the attack surface and slows the install.

## Code style

- Python 3.10+ syntax (`str | None`, structural pattern matching okay).
- `ruff` for formatting/linting. Line length 100.
- Type hints where they clarify intent; don't type-annotate obvious locals.
- Docstrings on public tool functions — they become the tool descriptions
  the LLM sees.

## Reporting stealth regressions

If a previously-passing target now blocks Cybr Ghost:

1. Confirm the target actually changed (try a second run, different locale).
2. Capture `snapshot()` output + a `screenshot()` from the failing run.
3. Open an issue with the target URL, repro steps, and the captured artifacts.
4. Label it `stealth-regression`.
