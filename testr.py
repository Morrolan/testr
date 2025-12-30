from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

import typer
from typer.main import get_command

typer_app = typer.Typer(help="Test Runner Dashboard powered by pytest + Trogon.")

try:
    from trogon import tui as trogon_tui

    _HAS_TROGON = True
except ModuleNotFoundError:  # pragma: no cover - runtime import guard
    trogon_tui = None
    _HAS_TROGON = False


@typer_app.command()
def dashboard(
    paths: Optional[List[str]] = typer.Argument(
        None, help="Paths or nodeids to test (default: tests/).", show_default="tests"
    ),
    keyword: Optional[str] = typer.Option(
        None, "-k", "--keyword", help="Only run tests matching this expression.", show_default=False
    ),
    markers: Optional[str] = typer.Option(
        None, "-m", "--markers", help="Only run tests with the given markers.", show_default=False
    ),
    extra: List[str] = typer.Option(
        [],
        "--extra",
        help="Additional raw pytest args (e.g. --maxfail=1 --lf).",
    ),
    use_last: bool = typer.Option(
        False,
        "--use-last",
        help="Reuse the most recently saved paths/filters and ignore the provided filters.",
    ),
    save_last: bool = typer.Option(
        True,
        "--save-last/--no-save-last",
        help="Save current paths/filters for reuse (default: save).",
    ),
    forget_last: bool = typer.Option(
        False,
        "--forget-last",
        help="Clear any saved paths/filters before running and do not save this run.",
    ),
) -> None:
    """Launch the live pytest dashboard."""
    paths = paths or ["tests"]
    from dashboard import PytestConfig, TestDashboardApp

    if forget_last:
        _clear_last_run()
        save_last = False

    if use_last:
        saved = _load_last_run()
        if saved:
            paths = saved.get("paths", paths)
            keyword = saved.get("keyword", keyword)
            markers = saved.get("markers", markers)
            extra = saved.get("extra", extra)
            typer.echo("Reusing saved filters/paths from the last run.")
        else:
            typer.echo("No saved filters found; running with provided/default values.")

    config = PytestConfig(paths=paths, keyword=keyword, markers=markers, extra=extra)

    if save_last:
        _save_last_run({"paths": paths, "keyword": keyword, "markers": markers, "extra": extra})

    TestDashboardApp(config).run()


_STATE_FILE = Path(__file__).resolve().parent / ".testr_last_run.json"


def _save_last_run(data: Dict) -> None:
    try:
        _STATE_FILE.write_text(json.dumps(data, indent=2))
    except OSError as exc:  # pragma: no cover - defensive guard
        typer.echo(f"Warning: failed to save last run config: {exc}", err=True)


def _load_last_run() -> Optional[Dict]:
    try:
        return json.loads(_STATE_FILE.read_text())
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as exc:  # pragma: no cover - defensive guard
        typer.echo(f"Warning: failed to read last run config: {exc}", err=True)
        return None


def _clear_last_run() -> None:
    try:
        _STATE_FILE.unlink(missing_ok=True)
    except OSError as exc:  # pragma: no cover - defensive guard
        typer.echo(f"Warning: failed to clear last run config: {exc}", err=True)


if not _HAS_TROGON:
    @typer_app.command("tui", help="Open Textual TUI (requires trogon; install via pip install -r requirements.txt).")
    def _tui_missing() -> None:
        typer.echo(
            "Trogon is not installed. Install it to use the TUI launcher:\n  pip install -r requirements.txt",
            err=True,
        )
        raise typer.Exit(code=1)


# Build a Click command from Typer and add Trogon's TUI entrypoint.
click_app = get_command(typer_app)
if _HAS_TROGON:
    click_app = trogon_tui(
        help="Open the Textual launcher for the pytest dashboard (interactive UI)."
    )(click_app)


def main() -> None:
    click_app()


if __name__ == "__main__":
    main()
