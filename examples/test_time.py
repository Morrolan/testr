import time

import pytest


def test_progressive_waits():
    start = time.perf_counter()
    for delay in (0.2, 0.3):
        time.sleep(delay)
    elapsed = time.perf_counter() - start
    assert elapsed >= 0.5


@pytest.mark.parametrize("delay", [0.1, 0.25, 0.35])
def test_parametrized_delays(delay):
    start = time.perf_counter()
    time.sleep(delay)
    elapsed = time.perf_counter() - start
    assert elapsed >= delay * 0.95


def test_batch_waits():
    delays = [0.1, 0.2, 0.25, 0.35]
    start = time.perf_counter()
    for delay in delays:
        time.sleep(delay)
    elapsed = time.perf_counter() - start
    assert elapsed >= sum(delays) * 0.95
