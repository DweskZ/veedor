"""`veedor registries ...` commands."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

import typer

from veedor.core.settings import get_settings
from veedor.infrastructure.registries import download as dl
from veedor.infrastructure.registries.sri import GHOST_SOURCE_NAME, build_ghost_companies, build_suppliers_sri
from veedor.infrastructure.registries.status import table_counts
from veedor.infrastructure.registries.supercias import build_supercias

app = typer.Typer(no_args_is_help=True)


class Source(StrEnum):
    sri = "sri"
    ghost = "ghost"
    supercias = "supercias"


def _selected(only: list[Source] | None) -> set[Source]:
    return set(only) if only else set(Source)


@app.command("download")
def download(
    only: Annotated[list[Source] | None, typer.Option(help="Restrict to sources (default: all).")] = None,
) -> None:
    """Download SRI RUC zips, the SRI ghost-company CSV and the Supercias CSVs into data/raw/."""
    raw = get_settings().raw_dir
    selected = _selected(only)
    report = lambda name, fresh: typer.echo(f"{'downloaded' if fresh else 'present   '} {name}")  # noqa: E731
    if selected & {Source.sri, Source.ghost}:
        rucs, ghost = dl.discover_sri()
        if Source.sri in selected:
            typer.echo(f"SRI page lists {len(rucs)} province files")
            dl.download_all(rucs, raw / "sri", report)
        if Source.ghost in selected:
            if ghost is None:
                typer.echo("Ghost-company CSV link not found on the SRI page.", err=True)
                raise typer.Exit(1)
            dl.download_all([ghost], raw / "sri", report)
    if Source.supercias in selected:
        dl.download_all(dl.supercias_files(), raw / "supercias", report)


@app.command("load")
def load(
    only: Annotated[list[Source] | None, typer.Option(help="Restrict to sources (default: all).")] = None,
) -> None:
    """Build the registry Parquet tables under data/lake/ from the raw files."""
    settings = get_settings()
    selected = _selected(only)
    if Source.sri in selected:
        result = build_suppliers_sri(settings.raw_dir / "sri", settings.lake_dir)
        typer.echo(
            f"suppliers_sri: {result.rows:,} rows from {result.files} files; matched "
            f"{result.matched_rucs:,}/{result.wanted_rucs:,} lake RUCs ({result.match_rate:.2%})"
        )
    if Source.ghost in selected:
        if (settings.raw_dir / "sri" / GHOST_SOURCE_NAME).exists():
            rows = build_ghost_companies(settings.raw_dir / "sri", settings.lake_dir)
            typer.echo(f"ghost_companies: {rows:,} rows")
        else:
            typer.echo("ghost_companies: skipped (raw file not downloaded)")
    if Source.supercias in selected:
        result = build_supercias(settings.raw_dir / "supercias", settings.lake_dir)
        typer.echo(
            f"companies_supercias: {result.companies:,} rows; "
            f"company_financials: {result.financials:,} rows; "
            f"matched {result.matched_rucs:,}/{result.wanted_rucs:,} lake RUCs ({result.match_rate:.2%})"
        )


@app.command("status")
def status() -> None:
    """Show row counts of the registry tables in the lake."""
    for table, rows in table_counts(get_settings().lake_dir).items():
        typer.echo(f"{table}: {'missing' if rows is None else f'{rows:,} rows'}")
