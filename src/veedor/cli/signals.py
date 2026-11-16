"""`veedor signals ...` commands."""

from __future__ import annotations

import typer

from veedor.core.settings import get_settings
from veedor.infrastructure.lake.marts_builder import LakeNotFoundError
from veedor.infrastructure.lake.marts_builder import build_marts as build_marts_sql
from veedor.infrastructure.lake.marts_builder_report import DuckDbMartsReport, MartsNotBuiltError
from veedor.use_cases import build_marts as use_case

app = typer.Typer(no_args_is_help=True)

YEAR_OPTION = typer.Option(None, help="Only processes of this year.")
METHOD_OPTION = typer.Option(None, help="Only this procurement method (exact name).")


def _print_summary(summary: dict) -> None:
    typer.echo(f"Built at {summary['built_at']} ({summary['duration_seconds']} s)")
    typer.echo("Lake rows:")
    for table, rows in summary["lake_rows"].items():
        typer.echo(f"  {table}: {rows:,}")
    typer.echo("Mart rows:")
    for mart, rows in summary["marts_rows"].items():
        typer.echo(f"  {mart}: {rows:,}")
    typer.echo("Signals:")
    for code, info in summary["signals"].items():
        if info["status"] == "computed":
            label = " (context)" if info.get("kind") == "context" else ""
            typer.echo(f"  {code}{label}: {info['fired']:,} fired")
        else:
            typer.echo(f"  {code}: {info['reason']}")
    skipped = [t for t in summary["thresholds"] if t["status"] != "used"]
    typer.echo(f"Thresholds: {len(summary['thresholds'])} method-years, {len(skipped)} not used")


@app.command("build")
def build() -> None:
    """Compute signals, risk scores and the three marts from the Parquet lake."""
    settings = get_settings()
    try:
        summary = use_case.build_marts(build_marts_sql, settings.lake_dir, settings.marts_dir)
    except LakeNotFoundError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    _print_summary(summary)


@app.command("summary")
def summary() -> None:
    """Print the summary of the last build."""
    report = DuckDbMartsReport(get_settings().marts_dir)
    try:
        _print_summary(use_case.get_build_summary(report))
    except MartsNotBuiltError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc


@app.command("top")
def top(
    limit: int = typer.Option(20, min=1, help="Number of processes to list."),
    year: int | None = YEAR_OPTION,
    method: str | None = METHOD_OPTION,
) -> None:
    """List the processes with the highest risk score."""
    report = DuckDbMartsReport(get_settings().marts_dir)
    try:
        rows = use_case.top_risk_processes(report, limit, year, method)
    except MartsNotBuiltError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    for row in rows:
        winner = "Persona natural" if row["winner_kind"] == "natural_person" else row["winner_name"]
        amount = f"{row['award_total']:,.0f}" if row["award_total"] is not None else "n/d"
        typer.echo(
            f"{row['risk_score']:5.1f}  {row['ocid']}  {row['year']}  {row['method']}  "
            f"{row['buyer_name']} -> {winner}  USD {amount}  [{', '.join(row['signal_codes'])}]"
        )
