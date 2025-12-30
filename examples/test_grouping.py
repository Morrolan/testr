import os
import pytest


DEMO_FAILURES = os.getenv("TESTR_DEMO_FAILURES", "").lower() in {"1", "true", "yes", "on"}


def test_feature_alpha_happy_path():
    assert "alpha".upper() == "ALPHA"


def test_feature_alpha_failure():
    # Grouped with the happy path above; helps demonstrate per-file grouping.
    expected = "ALPHa" if DEMO_FAILURES else "Alpha"
    assert "alpha".capitalize() == expected


@pytest.mark.xfail(strict=True, reason="Demonstrate expected failure reporting.")
def test_feature_beta_expected_failure():
    raise RuntimeError("Known issue #123")
