from __future__ import annotations

import asyncio
from typing import Dict, List

import pytest

from dashboard import (
    DashboardPlugin,
    PytestConfig,
    TestDashboardApp,
    _Emitter,
)


class FakeLog:
    def __init__(self) -> None:
        self.lines: List[str] = []

    def write_line(self, line: str, scroll_end=None):  # signature compat
        self.lines.append(line)

    def clear(self):
        self.lines.clear()


class FakeProgress:
    def __init__(self) -> None:
        self.calls: List[Dict] = []

    def update(self, **kwargs) -> None:
        self.calls.append(kwargs)


class FakeTable:
    def __init__(self) -> None:
        self.rows: List[tuple] = []
        self.cursor_type = None

    def clear(self):
        self.rows.clear()

    def add_row(self, *args, **kwargs):
        key = kwargs.get("key", f"row{len(self.rows)}")
        self.rows.append(args)
        return key

    def add_columns(self, *args, **kwargs):
        # no-op for tests
        return None


class FakeSummary:
    def __init__(self) -> None:
        self.last = None

    def update(self, content):
        self.last = content


def test_pytest_config_builds_default_args():
    cfg = PytestConfig()
    assert cfg.build_args()[:1] == ["tests"]
    assert "-q" in cfg.build_args()
    assert "--color=yes" in cfg.build_args()


def test_pytest_config_respects_overrides():
    cfg = PytestConfig(paths=["pkg"], keyword="slow", markers="smoke", extra=["--maxfail=1"])
    args = cfg.build_args(nodeids=["node::id"])
    assert args[:1] == ["node::id"]
    assert "-k" in args and "slow" in args
    assert "-m" in args and "smoke" in args
    assert "--maxfail=1" in args


def test_dashboard_plugin_emits_expected_events():
    seen = []
    plugin = DashboardPlugin(emit=seen.append)

    class Report:
        def __init__(self, failed=False):
            self.failed = failed
            self.nodeid = "node::test"
            self.fspath = "node.py"
            self.longrepr = "boom"
            self.longreprtext = "boom"
            self.outcome = "failed"
            self.duration = 0.1
            self.location = ("node.py", 1, "test")
            self.when = "call"

    plugin.pytest_collection_finish(type("Session", (), {"items": [1, 2, 3]}))
    plugin.pytest_collectreport(Report(failed=True))
    plugin.pytest_runtest_logstart("node::test", ("node.py", 1, "test"))
    plugin.pytest_runtest_logreport(Report(failed=True))
    plugin.pytest_sessionfinish(None, 0)

    event_types = [e["type"] for e in seen]
    assert event_types == ["collected", "collect_error", "start", "result", "finished"]


@pytest.mark.asyncio
async def test_emitter_pushes_events_into_queue():
    q: asyncio.Queue[Dict] = asyncio.Queue()
    emitter = _Emitter(q)
    emitter({"type": "ping"})
    event = await asyncio.wait_for(q.get(), timeout=1)
    assert event["type"] == "ping"


def test_dashboard_app_refresh_failures_groups_by_file():
    app = TestDashboardApp(PytestConfig(paths=["tests"]))
    app.fail_table = FakeTable()
    app.detail_log = FakeLog()
    app.failed_results = {
        "pkg/test_a.py::feature::case1": {},
        "pkg/test_a.py::feature::case2": {},
        "pkg/test_b.py::case3": {},
    }
    app._refresh_failures()
    rows = sorted(app.fail_table.rows)
    assert ("pkg/test_a.py :: feature", "2", "feature::case1, feature::case2") in rows
    assert ("pkg/test_b.py :: case3", "1", "case3") in rows


@pytest.mark.asyncio
async def test_dashboard_app_handle_result_tracks_progress():
    app = TestDashboardApp(PytestConfig(paths=["tests"]))
    app.progress_bar = FakeProgress()
    app.log_widget = FakeLog()
    app.summary_panel = FakeSummary()
    app.fail_table = FakeTable()
    app.detail_log = FakeLog()
    app.total_collected = 2

    await app._handle_result(
        {
            "nodeid": "pkg/test_mod.py::test_one",
            "outcome": "passed",
            "duration": 0.05,
            "location": ("pkg/test_mod.py", 1, "test_one"),
        }
    )
    assert app.completed == 1
    assert app.status_counts["passed"] == 1
    assert app.failed_results == {}

    await app._handle_result(
        {
            "nodeid": "pkg/test_mod.py::test_two",
            "outcome": "failed",
            "duration": 0.1,
            "location": ("pkg/test_mod.py", 2, "test_two"),
            "longrepr": "boom",
        }
    )
    assert app.completed == 2
    assert app.status_counts["failed"] == 1
    assert app.last_failed_nodeids == ["pkg/test_mod.py::test_two"]
    assert ("total" in app.progress_bar.calls[-1] and "progress" in app.progress_bar.calls[-1])


def test_dashboard_app_summary_text_contains_counts():
    app = TestDashboardApp(PytestConfig(paths=["tests"]))
    app.status_counts = {"passed": 2, "failed": 1, "skipped": 3}
    app.completed = 4
    app.total_collected = 5
    text = app._summary_text("extra info")
    assert "Passed" in text.plain
    assert "Failed" in text.plain
    assert "Progress" in text.plain
    assert "Coverage" in text.plain
    assert "40%" in text.plain
    assert "extra info" in text.plain


def test_run_pytest_invokes_pytest_main(monkeypatch):
    captured = {}

    def fake_main(args, plugins):
        captured["args"] = args
        captured["plugins"] = plugins
        return 0

    monkeypatch.setattr("dashboard.pytest.main", fake_main)
    app = TestDashboardApp(PytestConfig(paths=["alpha"]))
    app._run_pytest(emit=lambda _: None, nodeids=["a::b"])
    assert captured["args"][:1] == ["a::b"]
    assert captured["plugins"] and hasattr(captured["plugins"][0], "pytest_runtest_logreport")
