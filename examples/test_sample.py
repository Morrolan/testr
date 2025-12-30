import os
import time

import pytest


DEMO_FAILURES = os.getenv("TESTR_DEMO_FAILURES", "").lower() in {"1", "true", "yes", "on"}


def test_passing_math():
    assert 2 + 2 == 4


def test_failure_example():
    base = "dash" + "board"
    actual = base + "!" if DEMO_FAILURES else base
    # Enable demo failures via TESTR_DEMO_FAILURES=1 when you want a red row in the dashboard.
    assert "dashboard" == actual


@pytest.mark.skip(reason="Demonstrate skipped tests in the dashboard.")
def test_skipped_example():
    assert True


@pytest.mark.parametrize("value", [1, 2, 3])
def test_parametrized_progress(value):
    # Tiny sleep to make progress visible when running in the TUI.
    time.sleep(0.05)
    cap = 2 if DEMO_FAILURES else 3
    assert value <= cap
