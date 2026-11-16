"""`veedor quotes ...`: build the quotes mart, show a process's quotes, evaluate the selection."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import orjson
import typer

from veedor.core.settings import REPO_ROOT, get_settings
from veedor.use_cases.build_quotes import BATCH_PROCESSES, SIMILARITY_FLOOR, QuotesReport

app = typer.Typer(no_args_is_help=True)

SUMMARY_NAME = "process_quotes_build.json"
EVAL_PATH = REPO_ROOT / "eval" / "quotes.json"
DOC_PATH = REPO_ROOT / "docs" / "QUOTES.md"


def report_to_dict(report: QuotesReport) -> dict:
    return {
        "floor": report.floor,
        "processes": report.processes,
        "processes_with_quote": report.processes_with_quote,
        "texts": report.texts,
        "quotes": report.quotes,
        "quotes_with_pair": report.pairs,
        "near_duplicates_skipped": report.near_duplicates,
        "embedded_texts": report.embedded_texts,
        "name_vocabulary_tokens": report.name_vocabulary,
        "exclusions_by_reason": dict(sorted(report.reasons.items())),
        "by_signal": {
            code: {
                "processes": report.by_signal_processes[code],
                "with_quote": report.by_signal_with_quote[code],
                "quotes": report.by_signal_quotes[code],
            }
            for code in sorted(report.by_signal_processes)
        },
        "wall_seconds": round(report.wall_seconds, 1),
        "embed_seconds": round(report.embed_seconds, 1),
        "processes_per_second": round(report.processes_per_second, 1),
        "texts_per_second": round(report.texts_per_second, 1),
    }


@app.command("build")
def build(
    limit: Annotated[int | None, typer.Option(min=1, help="Only the first N processes (by ocid).")] = None,
    floor: Annotated[float, typer.Option(min=-1.0, max=1.0, help="Similarity floor.")] = SIMILARITY_FLOOR,
    batch_size: Annotated[int, typer.Option(min=1, help="Processes per embedding batch.")] = BATCH_PROCESSES,
    out: Annotated[Path | None, typer.Option(help="Marts directory (default: data/marts).")] = None,
) -> None:
    """Select up to three quotes per flagged process (idempotent; rewrites the two quotes marts)."""
    from veedor.infrastructure.quotes.source import LakeQuoteSource, MissingInputError
    from veedor.infrastructure.quotes.store import ParquetQuoteSink
    from veedor.infrastructure.vectors.embedding import FastEmbedEmbedder
    from veedor.use_cases.build_quotes import build_quotes

    settings = get_settings()
    marts = out or settings.marts_dir
    typer.echo("Loading the embedding model (cached locally)...")
    embedder = FastEmbedEmbedder()
    sink = ParquetQuoteSink(marts)

    def show(report: QuotesReport) -> None:
        typer.echo(
            f"  {report.processes:,} processes, {report.quotes:,} quotes, "
            f"{report.wall_seconds:,.0f} s, ~{report.processes_per_second:,.0f} processes/s"
        )

    try:
        report = build_quotes(
            LakeQuoteSource(
                settings.lake_dir, settings.marts_dir, settings.texts_dir, raw_path=settings.ocds_bulk_path
            ),
            embedder,
            sink,
            limit=limit,
            floor=floor,
            batch_size=batch_size,
            progress=show,
        )
    except MissingInputError as exc:
        sink.abort()
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    except BaseException:
        sink.abort()
        raise
    summary = report_to_dict(report)
    (marts / SUMMARY_NAME).write_bytes(orjson.dumps(summary, option=orjson.OPT_INDENT_2))
    typer.echo(
        f"processes {report.processes:,}; with a quote {report.processes_with_quote:,}; "
        f"quotes {report.quotes:,} ({report.pairs:,} with a paired answer); texts {report.texts:,}"
    )
    for reason, count in sorted(report.reasons.items()):
        typer.echo(f"  excluded {reason}: {count:,}")
    typer.echo(
        f"wall {report.wall_seconds:,.1f} s; embedding {report.embed_seconds:,.1f} s; "
        f"{report.processes_per_second:,.0f} processes/s, {report.texts_per_second:,.0f} texts/s"
    )


@app.command("show")
def show(ocid: Annotated[str, typer.Argument(help="Process identifier (ocds-5wno2w-...).")]) -> None:
    """Print the stored quotes of one process (read from the marts, no recomputation)."""
    import duckdb

    from veedor.infrastructure.quotes.store import QUOTES_TABLE, STATS_TABLE

    marts = get_settings().marts_dir
    quotes_path, stats_path = marts / f"{QUOTES_TABLE}.parquet", marts / f"{STATS_TABLE}.parquet"
    if not quotes_path.is_file() or not stats_path.is_file():
        typer.echo("The quotes marts are not built yet: run `veedor quotes build`.", err=True)
        raise typer.Exit(1)
    con = duckdb.connect(":memory:")
    stats = con.execute("SELECT * FROM read_parquet(?) WHERE ocid = ?", [str(stats_path), ocid]).fetchall()
    rows = con.execute(
        "SELECT rank, kind, text, date, author_kind, source_field, related_signal, similarity, truncated, "
        "pair_text, pair_kind, pair_source_field FROM read_parquet(?) WHERE ocid = ? ORDER BY rank",
        [str(quotes_path), ocid],
    ).fetchall()
    if not stats:
        typer.echo(f"{ocid}: no stored entry (not flagged, or without text).")
        raise typer.Exit(0)
    _, available, personal, unsafe, below, eligible, n_quotes = stats[0]
    typer.echo(
        f"{ocid}: {available} texts; excluded personal {personal}, unsafe {unsafe}; "
        f"below floor {below}; eligible {eligible}; quotes {n_quotes}"
    )
    for (
        rank,
        kind,
        text,
        date,
        author,
        source,
        signal,
        similarity,
        truncated,
        pair,
        pair_kind,
        pair_source,
    ) in rows:
        typer.echo(
            f"\n#{rank} [{kind}] {signal} similarity {similarity:.3f} {date or ''} ({author}) <{source}>"
        )
        typer.echo(f"  {text}{'  [truncated]' if truncated else ''}")
        if pair:
            typer.echo(f"  -> [{pair_kind}] <{pair_source}> {pair}")


@app.command("evaluate")
def evaluate(
    out: Annotated[Path, typer.Option(help="JSON output (numbers only).")] = EVAL_PATH,
    sample: Annotated[int, typer.Option(min=0, help="Quotes printed for manual reading.")] = 30,
    doc: Annotated[Path, typer.Option(help="Docs file whose generated block is refreshed.")] = DOC_PATH,
) -> None:
    """Coverage, exclusions, the label-free retrieval check and the privacy sweep over the real mart."""
    from veedor.infrastructure.quotes import evaluation

    result = evaluation.run_evaluation(get_settings(), sample=sample)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(orjson.dumps(result["numbers"], option=orjson.OPT_INDENT_2))
    typer.echo(orjson.dumps(result["numbers"], option=orjson.OPT_INDENT_2).decode())
    typer.echo(f"Wrote {out}")
    if evaluation.update_docs(doc, evaluation.render_markdown(result["numbers"])):
        typer.echo(f"Refreshed the generated block in {doc}")
    typer.echo("\n--- rarer name-pair candidates (sample) ---")
    for item in result["name_candidates"]:
        typer.echo(f"  - {item['text'][:220]}")
    if sample:
        typer.echo("\n--- sample for manual reading ---")
        for index, item in enumerate(result["sample"], 1):
            typer.echo(f"\n[{index}] {item['related_signal']} sim {item['similarity']:.2f} ({item['kind']})")
            typer.echo(f"    {item['text']}")
            if item["pair_text"]:
                typer.echo(f"    -> {item['pair_text']}")
