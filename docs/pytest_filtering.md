# Pytest Keywords and Markers (with code)

The dashboard filters tests using pytest keywords (`-k`) and markers (`-m`). Below are minimal code snippets and matching commands.

## Keywords (`-k`) match names/nodeids
`-k` evaluates a boolean expression against test nodeids (file::test_name). No decorators needed.

```python
# file: tests/test_login.py

def test_login_happy_path():
    ...

def test_login_slow_full_stack():
    ...

def test_logout_smoke():
    ...
```

Run by keyword:

```bash
# "login" in the name, but not "slow"
python testr.py dashboard tests -k "login and not slow"

# Either login or logout
python testr.py dashboard tests -k "login or logout"
```

## Markers (`-m`) match explicit tags
Markers are decorators; they’re the most reliable way to target subsets.

```python
# file: tests/test_api.py
import pytest

@pytest.mark.smoke
def test_get_user_smoke():
    ...

@pytest.mark.regression
def test_create_user_regression():
    ...

@pytest.mark.flaky
def test_occasional_timeout():
    ...
```

Run by marker:

```bash
# Only smoke
python testr.py dashboard tests -m smoke

# Smoke OR regression
python testr.py dashboard tests -m "smoke or regression"

# Smoke AND not flaky
python testr.py dashboard tests -m "smoke and not flaky"
```

## Mix keywords and markers
You can combine both selectors:

```bash
# Login tests that are smoke and not flaky
python testr.py dashboard tests -k login -m "smoke and not flaky"
```

## Register custom markers (avoid warnings)
Tell pytest your markers are intentional in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
markers = [
  "smoke: quick coverage",
  "regression: mainline flows",
  "flaky: unstable tests",
]
```

## Tips
- Prefer markers for durable suites (smoke/regression/integration); use `-k` for ad-hoc text matching.
- Name tests consistently (`test_login_*`) so `-k login` is predictable.
- When in doubt, run `python -m pytest -q --collect-only -k "<expr>"` to see what matches before using the dashboard.
