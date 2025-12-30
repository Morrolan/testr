# Test Runner Dashboard

A TUI dashboard for pytest that shows live progress, groups failures by file/feature, and lets you rerun failed tests with one key. Built with **Textual** and **Trogon**.

## Features
- Live pytest progress with counts and timings.
- Failure table grouped by file/feature.
- One-key reruns: `r` for failed-only, `a` for all.
- Trogon-powered launcher (`tui`) for interactive startup.

## Quickstart
1) Install (uses the repo’s `.venv`):
```bash
. .venv/bin/activate
pip install -r requirements.txt
```

2) Run the dashboard directly:
```bash
python testr.py dashboard examples
```

3) Or launch via Trogon UI:
```bash
python testr.py tui
```

## Keys in the Dashboard
- `r` — rerun failed tests only
- `s` — rerun selected failure row(s)
- `a` — rerun all tests
- `x` — stop the current run
- `q` — quit

Selecting a failure row shows its traceback in the “Failure Details” pane; rerunning with `s` uses only the selected nodeids.

## CLI Options
The `dashboard` command accepts a few common pytest filters:
- `paths` (positional): one or more paths/nodeids to run. Defaults to `tests`. You can point it at `examples` or a single test, e.g. `python testr.py dashboard examples/test_sample.py::test_passing_math`.
- `--keyword` / `-k`: pytest expression to select tests. Example: `python testr.py dashboard tests -k "slow and not db"`.
- `--markers` / `-m`: run only tests with matching markers. Example: `python testr.py dashboard tests -m "smoke or regression"`.
- `--extra`: pass through additional pytest args. Example: `python testr.py dashboard tests --extra --maxfail=1 --extra -q`.
- `--use-last`: reuse the most recently saved filters/paths (ignores currently provided filters if a saved set exists).
- `--save-last/--no-save-last`: control whether the current filters/paths are persisted for next time (defaults to saving).
- `--forget-last`: clear any saved filters/paths before running and skip saving this run.

### Quick pytest filtering cheatsheet (code examples)
```bash
# Keywords (-k) are boolean expressions over nodeids/test names/markers:
python testr.py dashboard tests -k "login and not slow"
python testr.py dashboard tests -k "api or ui"
python testr.py dashboard tests -k "smoke and get_user"

# Markers (-m) are explicit tags in code (e.g., @pytest.mark.smoke):
python testr.py dashboard tests -m smoke
python testr.py dashboard tests -m "smoke or regression"
python testr.py dashboard tests -m "smoke and not flaky"

# Register custom markers to avoid warnings (pyproject.toml):
[tool.pytest.ini_options]
markers = [
  "smoke: quick coverage",
  "regression: mainline flows",
  "flaky: unstable tests",
]
```

More detailed code-level examples of keywords and markers live in `docs/pytest_filtering.md`.

## Example Tests
Sample tests live in `examples/` to demo passes, fails, skips, and grouping:
- `examples/test_sample.py`
- `examples/test_grouping.py`

Set `TESTR_DEMO_FAILURES=1` when running the examples (or the dashboard pointed at `examples/`) to intentionally produce a couple of failures for the UI to display.

## Packaging
- Entry point: `testr-dashboard = app:main` (pyproject/PEP 621).
- Core deps: pytest, pytest-asyncio, typer, textual, trogon.

## Building standalones (PyInstaller)
- Install PyInstaller into your environment: `pip install pyinstaller`.
- On Linux/macOS terminals: run `./scripts/build_pyinstaller.sh`. It outputs `dist/testr`.
- On Windows PowerShell: `powershell -ExecutionPolicy Bypass -File scripts/build_pyinstaller.ps1`. It outputs `dist/testr.exe`.
- PyInstaller builds are OS-specific; create Linux binaries on Linux and Windows `.exe` files on Windows (no cross-compiling).
- The scripts collect Textual/Trogon assets automatically; point the resulting binary at your tests or `examples/` (optionally with `TESTR_DEMO_FAILURES=1`).
