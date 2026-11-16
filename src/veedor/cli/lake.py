"""`veedor lake ...` commands."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from veedor.core.settings import get_settings
from veedor.infrastructure.ocds.flatten import build_lake
from veedor.infrastructure.ocds.texts import build_texts

app = typer.Typer(no_args_is_help=True)


@app.command("build")
def build(
    source: Annotated[
        Path | None, typer.Option(help="Path to the SERCOP OCDS bulk file (.jsonl.gz).")
    ] = None,
    limit: Annotated[int | None, typer.Option(help="Only process the first N releases.")] = None,
    texts: Annotated[
        bool, typer.Option("--texts/--no-texts", help="Also write process_texts.parquet in the same pass.")
    ] = False,
) -> None:
    """Flatten the bulk file into processes/tenderers/awards Parquet tables."""
    settings = get_settings()
    counts = build_lake(
        source or settings.ocds_bulk_path,
        settings.lake_dir,
        limit=limit,
        with_texts=texts,
        texts_dir=settings.texts_dir,
    )
    for table, rows in counts.items():
        typer.echo(f"{table}: {rows:,} rows")


@app.command("build-texts")
def build_texts_command(
    source: Annotated[
        Path | None, typer.Option(help="Path to the SERCOP OCDS bulk file (.jsonl.gz).")
    ] = None,
    limit: Annotated[int | None, typer.Option(help="Only process the first N releases.")] = None,
) -> None:
    """Write process_texts.parquet (enquiry questions and answers, award texts) in one pass.

    The table holds unmasked source text: it is written to data/texts (outside the lake folder that
    compose mounts) and is never mounted into the API container."""
    settings = get_settings()
    summary = build_texts(source or settings.ocds_bulk_path, settings.texts_dir, limit=limit)
    megabytes = summary["bytes"] / 1e6
    typer.echo(f"process_texts: {summary['rows']:,} rows, {megabytes:,.1f} MB, {summary['seconds']} s")
    typer.echo(
        f"processes with at least one text: {summary['processes_with_text']:,} of {summary['releases']:,}"
    )
    for kind, rows in summary["rows_by_kind"].items():
        typer.echo(f"  {kind}: {rows:,}")
    for reason, rows in summary["dropped"].items():
        typer.echo(f"  dropped {reason}: {rows:,}")
