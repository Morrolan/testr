from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
import time
import threading
from typing import Callable, Dict, Iterable, List, Optional

import pytest
from _pytest.outcomes import Exit
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Footer, Header, Log, ProgressBar, Static, Button


@dataclass
class PytestConfig:
    """Simple container for pytest options we expose in the dashboard."""

    paths: List[str] = field(default_factory=lambda: ["tests"])
    keyword: Optional[str] = None
    markers: Optional[str] = None
    extra: List[str] = field(default_factory=list)

    def build_args(self, nodeids: Optional[Iterable[str]] = None) -> List[str]:
        """Construct the pytest CLI arguments for a run."""
        args: List[str] = []
        selected = list(nodeids or [])
        args.extend(selected if selected else self.paths)
        if self.keyword:
            args.extend(["-k", self.keyword])
        if self.markers:
            args.extend(["-m", self.markers])
        args.extend(self.extra)
        # quiet output keeps logs readable; color helps the Log widget
        args.extend(["-q", "--color=yes", "-s"])
        return args


class _Emitter:
    """Helper to push events from pytest threads into the asyncio loop."""

    def __init__(self, queue: asyncio.Queue[Dict]):
        self.queue = queue
        self.loop = asyncio.get_running_loop()

    def __call__(self, event: Dict) -> None:
        self.loop.call_soon_threadsafe(self.queue.put_nowait, event)


class DashboardPlugin:
    """Minimal pytest plugin that streams progress back to the dashboard."""

    def __init__(self, emit: Callable[[Dict], None], stop_event: Optional[threading.Event] = None):
        self.emit = emit
        self.stop_event = stop_event or threading.Event()

    def pytest_collection_finish(self, session):
        self.emit({"type": "collected", "total": len(session.items)})

    def pytest_collectreport(self, report):
        if report.failed:
            longrepr = getattr(report, "longreprtext", None) or str(report.longrepr)
            self.emit(
                {
                    "type": "collect_error",
                    "nodeid": report.nodeid or str(report.fspath),
                    "longrepr": longrepr,
                }
            )

    def pytest_runtest_logstart(self, nodeid, location):
        self.emit({"type": "start", "nodeid": nodeid, "location": location})

    def pytest_runtest_setup(self, item):
        if self.stop_event.is_set():
            raise Exit("Test run stopped by user.")

    def pytest_runtest_logreport(self, report):
        if report.when != "call":
            return
        if self.stop_event.is_set():
            report.outcome = "skipped"
            self.emit(
                {
                    "type": "result",
                    "nodeid": report.nodeid,
                    "outcome": "skipped",
                    "duration": 0,
                    "location": report.location,
                    "longrepr": "Stopped by user",
                }
            )
            raise Exit("Test run stopped by user.")
        longrepr = None
        if report.failed:
            longrepr = getattr(report, "longreprtext", None) or str(report.longrepr)
        self.emit(
            {
                "type": "result",
                "nodeid": report.nodeid,
                "outcome": report.outcome,
                "duration": report.duration,
                "location": report.location,
                "longrepr": longrepr,
            }
        )

    def pytest_sessionfinish(self, session, exitstatus):
        self.emit({"type": "finished", "status": exitstatus})


class StopModal(ModalScreen[None]):
    """Simple modal to show when a run is stopped."""

    BINDINGS = [Binding("escape", "dismiss", "Close", show=False)]

    def compose(self) -> ComposeResult:  # type: ignore[override]
        yield Container(
            Static("Test run stopped by user.", classes="panel-title"),
            Static("The current pytest run was halted. You can start a new run anytime.", id="stop-message"),
            Container(
                Button("OK", id="stop-ok", variant="primary"),
                classes="modal-buttons",
            ),
            classes="modal-surface",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "stop-ok":
            self.dismiss()


class TestDashboardApp(App):
    """Textual dashboard for live pytest runs."""

    TITLE = "Testr - v0.0.1"
    SUB_TITLE = "PyTest Runner Dashboard"
    __test__ = False  # prevent pytest from collecting this as a test case

    CSS = """
    Screen {
        layout: vertical;
    }

    #content {
        padding: 1 2;
        layout: vertical;
    }

    #summary {
        height: 3;
        content-align: left middle;
        padding: 0 1;
        border: round $accent;
    }

    #progress {
        height: 3;
        padding: 0 1;
    }

    #main {
        layout: horizontal;
        height: 1fr;
        margin-top: 1;
    }

    #log-panel, #fail-panel, #detail-panel {
        border: round $accent;
        height: 1fr;
    }

    #log-panel > Log, #fail-panel > DataTable, #detail-panel > Log {
        height: 1fr;
    }

    #help {
        height: auto;
        margin-top: 1;
        color: $secondary;
    }

    .modal-surface {
        border: round $accent;
        background: $surface;
        color: $text;
        padding: 1 2;
        width: 30%;
        min-width: 30;
        max-width: 60;
        height: auto;
        max-height: 12;
        min-height: 5;
        align: center middle;
        content-align: center middle;
    }

    StopModal {
        align: center middle;
    }

    .modal-buttons {
        width: 100%;
        content-align: center middle;
        padding-top: 1;
    }
    """

    BINDINGS = [
        Binding("r", "rerun_failed", "Rerun failed"),
        Binding("s", "rerun_selected", "Rerun selected"),
        Binding("a", "rerun_all", "Run all tests"),
        Binding("x", "stop_run", "Stop run"),
        Binding("q", "quit", "Quit"),
        Binding("ctrl+q", "quit", "Quit"),
        Binding("escape", "quit", "Quit", show=False),
    ]

    def __init__(self, config: PytestConfig, **kwargs):
        super().__init__(**kwargs)
        self.config = config
        self.event_queue: asyncio.Queue[Dict] = asyncio.Queue()
        self.runner_task: Optional[asyncio.Task] = None
        self.consumer_task: Optional[asyncio.Task] = None
        self.total_collected: Optional[int] = None
        self.completed: int = 0
        self.status_counts: Dict[str, int] = defaultdict(int)
        self.failed_results: Dict[str, Dict] = {}
        self.last_failed_nodeids: List[str] = []
        self.failure_group_map: Dict[str, List[str]] = {}
        self.selected_nodeids: List[str] = []
        
        self.summary_panel = Static(id="summary")
        self.progress_bar = ProgressBar(id="progress")
        self.log_widget = Log(id="log")
        self.fail_table = DataTable(id="failures", zebra_stripes=True)
        self.fail_table.cursor_type = "row"
        self.detail_log = Log(id="detail-log")
        self.help_text = Static(
            "r = rerun failures · s = rerun selected · a = run all · x = stop run · q = quit. Showing pytest progress in real time.",
            id="help",
        )
        self.run_started_at: Optional[float] = None
        self.stop_event = threading.Event()
        self.stop_modal: Optional[StopModal] = None

    def compose(self) -> ComposeResult:  # type: ignore[override]
        yield Header(show_clock=True)
        yield Container(
            self.summary_panel,
            self.progress_bar,
            Horizontal(
                Vertical(
                    Static("Live Output", classes="panel-title"),
                    Container(self.log_widget, id="log-panel"),
                ),
                Vertical(
                    Static("Failures by file / feature", classes="panel-title"),
                    Container(self.fail_table, id="fail-panel"),
                ),
                Vertical(
                    Static("Failure Details", classes="panel-title"),
                    Container(self.detail_log, id="detail-panel"),
                ),
                id="main",
            ),
            self.help_text,
            id="content",
        )
        yield Footer()

    async def on_mount(self) -> None:
        self.fail_table.add_columns("File / Feature", "Count", "Tests")
        self._update_summary("Waiting to collect tests…")
        await self.start_new_run()

    async def start_new_run(self, failed_only: bool = False) -> None:
        if self.runner_task and not self.runner_task.done():
            self.log_widget.write_line("A run is already active; ignoring new request.")
            return

        # Reset state for a fresh run.
        targets = list(self.last_failed_nodeids) if failed_only else None
        self.failed_results.clear()
        if not failed_only:
            self.last_failed_nodeids.clear()
        self.failure_group_map.clear()
        self.selected_nodeids = []
        self.completed = 0
        self.total_collected = None
        self.status_counts = defaultdict(int)
        self.log_widget.clear()
        self.fail_table.clear()
        self.detail_log.clear()
        self.progress_bar.update(total=None, progress=0)
        context = "failed tests" if failed_only else "full suite"
        self.log_widget.write_line(f"Starting {context} run…")
        self._update_summary("Collecting tests…")
        self.run_started_at = time.monotonic()
        self.stop_event.clear()

        # Spin up event handling and pytest worker.
        self.event_queue = asyncio.Queue()
        emitter = _Emitter(self.event_queue)

        async def consume() -> None:
            await self._consume_events()

        async def worker() -> None:
            await asyncio.to_thread(self._run_pytest, emitter, targets, self.stop_event)

        self.consumer_task = asyncio.create_task(consume())
        self.runner_task = asyncio.create_task(worker())

    def _run_pytest(
        self, emit: _Emitter, nodeids: Optional[List[str]], stop_event: Optional[threading.Event] = None
    ) -> None:
        args = self.config.build_args(nodeids)
        plugin = DashboardPlugin(emit, stop_event or self.stop_event)
        emit({"type": "args", "args": args})
        pytest.main(args, plugins=[plugin])

    async def _consume_events(self) -> None:
        while True:
            event = await self.event_queue.get()
            event_type = event.get("type")
            if event_type == "collected":
                self.total_collected = int(event.get("total", 0))
                self.progress_bar.update(total=float(self.total_collected), progress=0)
                self._update_summary("Collected tests, running…")
                self.log_widget.write_line(f"Collected {self.total_collected} tests.")
            elif event_type == "start":
                self.log_widget.write_line(f"▶ {event.get('nodeid')}")
            elif event_type == "result":
                await self._handle_result(event)
            elif event_type == "collect_error":
                nodeid = event.get("nodeid", "collection")
                longrepr = event.get("longrepr", "")
                self.log_widget.write_line(f"[!] Collection error in {nodeid}")
                self.failed_results[nodeid] = {
                    "nodeid": nodeid,
                    "outcome": "failed",
                    "longrepr": longrepr,
                }
                self._refresh_failures()
            elif event_type == "args":
                args = " ".join(event.get("args", []))
                self.log_widget.write_line(f"pytest {args}")
            elif event_type == "finished":
                status = event.get("status")
                if not self.failed_results:
                    self.last_failed_nodeids.clear()
                if status == "stopped":
                    summary = "Run stopped by user."
                elif status is not None:
                    summary = f"Run complete (exit status {status})."
                else:
                    summary = "Run complete."
                self._update_summary(summary)
                self.log_widget.write_line(summary)
                return

    async def _handle_result(self, event: Dict) -> None:
        nodeid = str(event.get("nodeid"))
        outcome = str(event.get("outcome"))
        self.completed += 1
        self.status_counts[outcome] += 1
        progress_target = float(self.total_collected or max(self.completed, 1))
        self.progress_bar.update(total=progress_target, progress=float(self.completed))
        duration_ms = float(event.get("duration", 0.0)) * 1000
        msg = f"{nodeid} [{outcome}] ({duration_ms:.1f} ms)"
        self.log_widget.write_line(msg)

        if outcome in {"failed", "error"}:
            self.failed_results[nodeid] = event
            self.last_failed_nodeids = list(self.failed_results.keys())
            self._refresh_failures()
        self._update_summary()

    def _refresh_failures(self) -> None:
        grouped: Dict[str, List[str]] = defaultdict(list)
        group_nodeids: Dict[str, List[str]] = defaultdict(list)
        for nodeid in self.failed_results:
            parts = nodeid.split("::")
            file_part = parts[0]
            feature = parts[1] if len(parts) > 1 else parts[0]
            group_key = f"{file_part} :: {feature}"
            grouped[group_key].append("::".join(parts[1:]) or parts[0])
            group_nodeids[group_key].append(nodeid)

        self.fail_table.clear()
        self.failure_group_map.clear()
        first_row_key = None
        for group, tests in grouped.items():
            compact = ", ".join(sorted(tests))
            row_key = self.fail_table.add_row(group, str(len(tests)), compact)
            if first_row_key is None:
                first_row_key = row_key
            self.failure_group_map[row_key] = group_nodeids[group]

        # Auto-populate details with the first row if present.
        if first_row_key is not None:
            self._update_failure_details(first_row_key)

    def _summary_text(self, extra: str = "") -> Text:
        passed = self.status_counts.get("passed", 0)
        failed = self.status_counts.get("failed", 0) + self.status_counts.get(
            "error", 0
        )
        skipped = self.status_counts.get("skipped", 0)
        total_display = self.total_collected if self.total_collected is not None else "?"
        elapsed = self._format_duration(time.monotonic() - self.run_started_at) if self.run_started_at else "0s"
        eta_display = "…"
        if self.run_started_at and self.total_collected and self.completed > 0:
            remaining = max(self.total_collected - self.completed, 0)
            rate = (time.monotonic() - self.run_started_at) / max(self.completed, 1)
            eta_seconds = remaining * rate
            eta_display = self._format_duration(eta_seconds)
        coverage_display = "?"
        if self.total_collected and self.total_collected > 0:
            coverage_percent = (passed / self.total_collected) * 100
            coverage_display = f"{coverage_percent:.0f}%"
        base = (
            f"[green]Passed[/]: {passed}   "
            f"[red]Failed[/]: {failed}   "
            f"[yellow]Skipped[/]: {skipped}   "
            f"[cyan]Progress[/]: {self.completed}/{total_display}   "
            f"[magenta]Elapsed[/]: {elapsed}   "
            f"[blue]ETA[/]: {eta_display}   "
            f"[white]Coverage[/]: {coverage_display}"
        )
        if extra:
            base = f"{base}\n{extra}"
        return Text.from_markup(base)

    def _update_summary(self, extra: str = "") -> None:
        self.summary_panel.update(self._summary_text(extra))

    async def action_rerun_failed(self) -> None:
        if not self.last_failed_nodeids:
            self.log_widget.write_line("No failed tests to rerun.")
            return
        await self.start_new_run(failed_only=True)

    async def action_rerun_selected(self) -> None:
        if not self.selected_nodeids:
            self.log_widget.write_line("No failure row selected; rerunning all failures instead.")
            await self.action_rerun_failed()
            return
        self.last_failed_nodeids = list(self.selected_nodeids)
        await self.start_new_run(failed_only=True)

    async def action_rerun_all(self) -> None:
        await self.start_new_run(failed_only=False)

    def _update_failure_details(self, row_key) -> None:
        nodeids = self.failure_group_map.get(row_key, [])
        self.selected_nodeids = nodeids
        self.detail_log.clear()
        if not nodeids:
            self.detail_log.write_line("No details available for this row.")
            return
        for nodeid in nodeids:
            self.detail_log.write_line(f"[bold]{nodeid}[/]")
            result = self.failed_results.get(nodeid, {})
            longrepr = result.get("longrepr")
            if longrepr:
                self.detail_log.write_line(str(longrepr))
            else:
                self.detail_log.write_line("No traceback recorded.")
            self.detail_log.write_line("-" * 40)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self._update_failure_details(event.row_key)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self._update_failure_details(event.row_key)

    async def action_stop_run(self) -> None:
        if not self.runner_task or self.runner_task.done():
            self.log_widget.write_line("No active run to stop.")
            return
        self.stop_event.set()
        self._clear_event_queue()
        self.log_widget.write_line("Stop requested; attempting to cancel current run…")
        self._update_summary("Stopping run…")
        try:
            self.event_queue.put_nowait({"type": "finished", "status": "stopped"})
        except asyncio.QueueFull:
            pass
        await self._show_stop_modal()

    def _clear_event_queue(self) -> None:
        try:
            while True:
                self.event_queue.get_nowait()
        except asyncio.QueueEmpty:
            return

    async def _show_stop_modal(self) -> None:
        if self.stop_modal and self.stop_modal.is_running:
            return
        self.stop_modal = StopModal()
        await self.push_screen(self.stop_modal)

    @staticmethod
    def _format_duration(seconds: float) -> str:
        seconds = max(0, int(seconds))
        hours, remainder = divmod(seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        if hours:
            return f"{hours}h{minutes:02d}m{secs:02d}s"
        if minutes:
            return f"{minutes}m{secs:02d}s"
        return f"{secs}s"
