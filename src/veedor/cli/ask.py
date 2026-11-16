"""`veedor ask <ocid> "<question>"`: ask one question about one process from the command line."""

from __future__ import annotations

from typing import Annotated

import typer


def ask(
    ocid: Annotated[str, typer.Argument(help="Process identifier (ocds-5wno2w-...).")],
    question: Annotated[str, typer.Argument(help="One question in Spanish, 3 to 300 characters.")],
    no_model: Annotated[bool, typer.Option("--no-model", help="Answer by retrieval only.")] = False,
) -> None:
    """Answer from the stored evidence of the process; each sentence shows its source."""
    from veedor.api.ask_wiring import build_service
    from veedor.core.settings import get_settings
    from veedor.infrastructure.lake.reader import LakeReader
    from veedor.use_cases.ask import InvalidQuestionError
    from veedor.use_cases.queries.ports import NotFoundError

    settings = get_settings()
    if no_model:
        settings = settings.model_copy(update={"llm_api_key": None})
    service = build_service(settings, LakeReader(settings.lake_dir, settings.marts_dir))
    try:
        answer = service.ask(ocid, question)
    except InvalidQuestionError as exc:
        typer.echo(f"Invalid question: {exc.problem.value}", err=True)
        raise typer.Exit(2) from exc
    except NotFoundError as exc:
        typer.echo("Process not found.", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"[{answer.mode}] {answer.reason.value}")
    for sentence in answer.sentences:
        typer.echo(f"- {sentence.text}  ({sentence.source_id}: {sentence.source_field})")
    for quote in answer.quotes:
        typer.echo(f"  «{quote.text}» ({quote.kind}, {quote.source_field})")
    typer.echo(answer.note_es)
