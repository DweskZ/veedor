"""`veedor vectors ...`: build, inspect and evaluate the process vector index."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import orjson
import typer

from veedor.core.settings import REPO_ROOT, get_settings
from veedor.use_cases.build_vectors import DEFAULT_CHUNK, Progress
from veedor.use_cases.similar_processes import VectorsUnavailable

app = typer.Typer(no_args_is_help=True)

EVAL_PATH = REPO_ROOT / "eval" / "vector_search.json"
DOC_PATH = REPO_ROOT / "docs" / "VECTOR_SEARCH.md"


def _store():
    from veedor.infrastructure.vectors.repository import PgVectorStore

    return PgVectorStore.from_settings()


@app.command("build")
def build(
    limit: Annotated[
        int | None, typer.Option(min=1, help="Only the first N in-scope processes (by ocid).")
    ] = None,
    batch_size: Annotated[int, typer.Option(min=1, help="Texts per ONNX batch.")] = 64,
    chunk_size: Annotated[
        int, typer.Option(min=1, help="Unique texts embedded and committed per step.")
    ] = DEFAULT_CHUNK,
    threads: Annotated[int | None, typer.Option(min=1, help="ONNX intra-op threads per worker.")] = None,
    workers: Annotated[int | None, typer.Option(min=2, help="Data-parallel embedding workers.")] = None,
) -> None:
    """Embed every non-catalogue process (idempotent: unchanged text + same model is skipped)."""
    from veedor.infrastructure.vectors.embedding import FastEmbedEmbedder
    from veedor.infrastructure.vectors.source import LakeProcessSource
    from veedor.use_cases.build_vectors import build_vectors

    settings = get_settings()
    source = LakeProcessSource(settings.lake_dir, settings.marts_dir)
    typer.echo("Loading the embedding model (cached locally after the first download)...")
    embedder = FastEmbedEmbedder(batch_size=batch_size, threads=threads, parallel=workers)

    def show(progress: Progress) -> None:
        rate = progress.done / progress.elapsed if progress.elapsed else 0.0
        typer.echo(
            f"  {progress.done:,}/{progress.total:,} unique texts "
            f"({progress.done / progress.total:.0%}), {progress.elapsed:,.0f} s, ~{rate:,.0f} texts/s"
        )

    try:
        report = build_vectors(source, embedder, _store(), limit=limit, chunk_size=chunk_size, progress=show)
    except FileNotFoundError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    except VectorsUnavailable as exc:
        typer.echo(f"Vector database unavailable: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(
        f"records seen {report.records_seen:,}; unchanged (skipped) {report.unchanged_skipped:,}; "
        f"embedded/upserted {report.records_embedded:,}; unique texts embedded {report.unique_texts:,} "
        f"(duplicates avoided: {report.records_embedded - report.unique_texts:,})"
    )
    for status, count in sorted(report.statuses.items()):
        typer.echo(f"  {status}: {count:,}")
    typer.echo(
        f"wall {report.wall_seconds:,.1f} s; embedding {report.embed_seconds:,.1f} s "
        f"({report.texts_per_second:,.0f} unique texts/s); {report.rows_per_second:,.0f} rows/s end to end"
    )


@app.command("status")
def status() -> None:
    """Rows, model, dimension, index and last build time."""
    from veedor.infrastructure.vectors.embedding import DIMENSION

    try:
        info = _store().status()
    except VectorsUnavailable as exc:
        typer.echo(f"Vector index unavailable: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"rows: {info.rows:,}")
    typer.echo(f"models: {', '.join(f'{m} ({n:,})' for m, n in info.models.items()) or 'none'}")
    typer.echo(f"dimension: {DIMENSION}")
    typer.echo(f"index: {info.index_definition or 'missing'}")
    typer.echo(f"last build: {info.last_build.isoformat() if info.last_build else 'never'}")


@app.command("evaluate")
def evaluate(
    sample: Annotated[
        int, typer.Option(min=100, help="Query processes (at least 1,000 for the contract).")
    ] = 1_000,
    pool: Annotated[int, typer.Option(min=1_000, help="Pool size for the CPC-leakage experiment.")] = 20_000,
    out: Annotated[Path, typer.Option(help="JSON output.")] = EVAL_PATH,
    doc: Annotated[Path, typer.Option(help="Docs file whose generated block is refreshed.")] = DOC_PATH,
) -> None:
    """CPC-proxy retrieval quality, baselines, leakage check and latency; writes eval/vector_search.json."""
    from veedor.infrastructure.vectors import evaluation
    from veedor.infrastructure.vectors.embedding import FastEmbedEmbedder
    from veedor.infrastructure.vectors.source import LakeProcessSource

    settings = get_settings()
    try:
        result = evaluation.run_evaluation(
            _store(), LakeProcessSource(settings.lake_dir, settings.marts_dir), FastEmbedEmbedder(),
            sample=sample, pool_size=pool,
        )  # fmt: skip
    except (VectorsUnavailable, FileNotFoundError) as exc:
        typer.echo(f"Cannot evaluate: {exc}", err=True)
        raise typer.Exit(1) from exc
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(orjson.dumps(result, option=orjson.OPT_INDENT_2))
    typer.echo(orjson.dumps(result, option=orjson.OPT_INDENT_2).decode())
    typer.echo(f"Wrote {out}")
    if evaluation.update_docs(doc, evaluation.render_markdown(result)):
        typer.echo(f"Refreshed the generated block in {doc}")
