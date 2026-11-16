"""`veedor dossier ...`: build evidence dossiers, batch them and inspect run traces."""

from __future__ import annotations

import json
from typing import Annotated

import duckdb
import typer

from veedor.agents.investigator.tracing import TraceWriter, summarise
from veedor.core.settings import get_settings
from veedor.domain.dossier.errors import ProcessNotFoundError
from veedor.domain.dossier.models import Dossier
from veedor.infrastructure.investigations.store import valid_ocid
from veedor.use_cases.build_dossier import default_service

app = typer.Typer(help="Build evidence dossiers.", no_args_is_help=True)


def render_text(dossier: Dossier) -> str:
    report = dossier.grounding_report
    lines = [
        f"# Dossier {dossier.ocid}",
        f"Modo: {dossier.mode} | verificación: {'aprobada' if report.passed else 'rechazada'} "
        f"({report.n_checked} elementos comprobados) | intentos LLM: {dossier.llm_attempts}",
        "",
        dossier.summary_es,
    ]
    for section in dossier.sections:
        lines += ["", f"## {section.title}", section.body]
    lines += ["", "## Fuentes"]
    for s in dossier.sources:
        lines.append(
            f"- {s.dataset} | {s.licence or 'licencia no disponible'} | consulta: "
            f"{s.retrieved_at or 'no disponible'} | registro: {s.record_id or 'no disponible'}"
        )
    return "\n".join(lines)


def check_ocid(ocid: str) -> None:
    """One-line message and exit code 2 for an identifier that can never name a process."""
    if not valid_ocid(ocid):
        typer.echo(
            "Identificador de proceso no válido (vacío, demasiado largo o con caracteres de control).",
            err=True,
        )
        raise typer.Exit(2)


@app.command("build")
def build(
    ocid: str,
    print_: Annotated[bool, typer.Option("--print", help="Print the dossier text.")] = False,
    refresh: Annotated[bool, typer.Option(help="Ignore the cached dossier.")] = False,
    no_llm: Annotated[bool, typer.Option("--no-llm", help="Force template mode.")] = False,
) -> None:
    """Build (or load from cache) the dossier of one process."""
    check_ocid(ocid)
    try:
        dossier = default_service(use_llm=not no_llm).build(ocid, refresh=refresh)
    except ProcessNotFoundError:
        typer.echo(f"Proceso no encontrado: {ocid}", err=True)
        raise typer.Exit(1) from None
    if print_:
        typer.echo(render_text(dossier))
    else:
        typer.echo(f"{dossier.ocid}: modo={dossier.mode} verificación={dossier.grounding_report.passed}")


def _top_ocids(n: int) -> list[str]:
    path = get_settings().marts_dir / "process_scores.parquet"
    if not path.is_file():
        typer.echo(f"Falta {path}; ejecute primero `veedor signals build`.", err=True)
        raise typer.Exit(1)
    con = duckdb.connect(":memory:")
    rows = con.execute(
        "SELECT ocid FROM read_parquet(?) ORDER BY risk_score DESC, n_signals DESC, ocid LIMIT ?",
        [str(path), n],
    ).fetchall()
    return [r[0] for r in rows]


@app.command("batch")
def batch(
    top: Annotated[int, typer.Option(help="Number of highest-risk processes.")] = 20,
    refresh: Annotated[bool, typer.Option(help="Ignore cached dossiers.")] = True,
    no_llm: Annotated[bool, typer.Option("--no-llm", help="Force template mode.")] = False,
) -> None:
    """Build dossiers for the N highest-risk processes and print the grounding pass rate."""
    service = default_service(use_llm=not no_llm)
    writer = TraceWriter(get_settings().data_dir / "traces")
    already = len(writer.read())
    dossiers: list[Dossier] = []
    errors = 0
    for ocid in _top_ocids(top):
        try:
            dossiers.append(service.build(ocid, refresh=refresh))
        except Exception as exc:  # noqa: BLE001 - keep the batch going, report at the end
            errors += 1
            typer.echo(f"error {ocid}: {type(exc).__name__}", err=True)
    traces = writer.read()[already:]
    passed = sum(d.grounding_report.passed for d in dossiers)
    typer.echo(f"Dossiers generados: {len(dossiers)} | errores: {errors}")
    typer.echo(f"Verificación aprobada: {passed}/{len(dossiers)} ({passed / max(len(dossiers), 1):.0%})")
    typer.echo(json.dumps({k: v for k, v in summarise(traces).items()}, ensure_ascii=False, indent=2))
    examples = [r for t in traces for a in t.attempt_log for r in a.get("rejected", [])][:8]
    if examples:
        typer.echo(
            "Ejemplos de elementos rechazados por el verificador: " + json.dumps(examples, ensure_ascii=False)
        )


@app.command("traces")
def traces(
    summary: Annotated[bool, typer.Option("--summary", help="Print aggregate figures.")] = True,
) -> None:
    """Summarise the investigator run traces (data/traces/investigator.jsonl)."""
    records = TraceWriter(get_settings().data_dir / "traces").read()
    if not records:
        typer.echo("Sin trazas registradas.")
        return
    if summary:
        typer.echo(json.dumps(summarise(records), ensure_ascii=False, indent=2))
