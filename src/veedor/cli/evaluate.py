"""`veedor evaluate ...` commands: back-test, coverage and the generated report."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Annotated

import orjson
import typer

from veedor.core.settings import REPO_ROOT, get_settings
from veedor.evaluation import backtest, coverage, history, report

app = typer.Typer(no_args_is_help=True)

EVAL_DIR = REPO_ROOT / "eval"
DOC_PATH = REPO_ROOT / "docs" / "EVALUATION.md"


def _json_default(value: object) -> float:
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(type(value))


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        orjson.dumps(payload, default=_json_default, option=orjson.OPT_INDENT_2 | orjson.OPT_SERIALIZE_NUMPY)
    )


def _read_json(path: Path) -> dict:
    if not path.exists():
        typer.echo(f"Missing {path}. Run the matching `veedor evaluate` command first.", err=True)
        raise typer.Exit(1)
    return orjson.loads(path.read_bytes())


@app.command("backtest")
def run_backtest(
    n_boot: Annotated[int, typer.Option(min=100, help="Bootstrap replicates.")] = backtest.DEFAULT_N_BOOT,
    seed: Annotated[int, typer.Option(help="Random seed.")] = backtest.DEFAULT_SEED,
    out_dir: Annotated[Path, typer.Option(help="Directory for the JSON/CSV outputs.")] = EVAL_DIR,
    note: Annotated[str, typer.Option(help="What changed in the rules/data since the last run.")] = "",
    record_history: Annotated[
        bool, typer.Option(help="Append this run to eval/history.json (skip for non-rule reruns).")
    ] = True,
) -> None:
    """Positive-unlabelled back-test against the SRI ghost-company list; writes eval/backtest.json."""
    settings = get_settings()
    try:
        result = backtest.run_backtest(settings.lake_dir, settings.marts_dir, n_boot, seed)
    except (FileNotFoundError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    if record_history:
        entry = history.entry_from(result, note or "No change description given.")
        result["history"] = history.append(out_dir / "history.json", entry)
    else:
        result["history"] = history.load(out_dir / "history.json")
    _write_json(out_dir / "backtest.json", result)
    report.write_csvs(result, out_dir)
    typer.echo(report.summary_text(result))
    typer.echo(f"Wrote {out_dir / 'backtest.json'}")


@app.command("coverage")
def run_coverage(
    out_dir: Annotated[Path, typer.Option(help="Directory for the JSON/CSV outputs.")] = EVAL_DIR,
) -> None:
    """Descriptive coverage of the signals (no labels); writes eval/coverage.json."""
    settings = get_settings()
    try:
        result = coverage.run_coverage(settings.lake_dir, settings.marts_dir)
    except FileNotFoundError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    _write_json(out_dir / "coverage.json", result)
    report.write_coverage_csvs(result, out_dir)
    typer.echo(coverage.summary_text(result))
    typer.echo(f"Wrote {out_dir / 'coverage.json'}")


@app.command("qa")
def run_qa(
    with_model: Annotated[
        bool, typer.Option("--with-model", help="Also run model mode (needs provider, model name and key).")
    ] = False,
    n: Annotated[int, typer.Option(min=300, help="Processes sampled (at least 300).")] = 600,
    model: Annotated[str | None, typer.Option(help="Model name, when VEEDOR_LLM_MODEL is not set.")] = None,
    out_dir: Annotated[Path, typer.Option(help="Directory for eval/qa.json.")] = EVAL_DIR,
    doc: Annotated[Path, typer.Option(help="Markdown file with the generated QA block.")] = DOC_PATH,
    heldout: Annotated[
        bool,
        typer.Option(
            "--heldout/--no-heldout",
            help="FINAL REPORT ONLY: also evaluate the second held-out set and the held-out adversarial "
            "set, once (needs the shipped thresholds; refused when already evaluated). Without it they are "
            "carried over from the previous eval/qa.json; the first held-out set is never re-run (it "
            "measured intents-v1). `heldout_runs` in eval/qa.json counts every run of every held-out set.",
        ),
    ] = False,
) -> None:
    """Question answering: retrieval-only over >= 300 processes, model mode over ~150 questions."""
    from veedor.evaluation.qa import render, runner

    settings = get_settings()
    if model:
        settings = settings.model_copy(update={"llm_model": model})
    if with_model and not settings.model_configured:
        typer.echo("No model is configured (provider, model name and key): running retrieval only.", err=True)
    previous = out_dir / "qa.json"
    # A scratch --out-dir still carries the held-out numbers of the real file.
    carry_from = previous if previous.is_file() else EVAL_DIR / "qa.json"
    previous_result = orjson.loads(carry_from.read_bytes()) if carry_from.is_file() else {}
    try:
        result = runner.run_evaluation(
            settings,
            with_model=with_model,
            n=n,
            heldout=heldout,
            previous=previous_result,
            progress=typer.echo,
        )
    except (FileNotFoundError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    if not with_model and carry_from.is_file():
        # Model mode is not rerun (cost): keep its stored numbers, marked as measured on the original
        # (in-vocabulary) phrasings and the sample of that run.
        old = previous_result.get("model")
        if old and old.get("status") == "ran":
            old["measured_on"] = "in_vocabulary_phrasings"
            old["measured_with"] = "the earlier key-phrase retrieval; not rerun with the intent retrieval"
            old["carried_over"] = True
            result["model"] = old
    _write_json(out_dir / "qa.json", result)
    render.update_docs(doc, render.render_markdown(result))
    adv = result["retrieval_only"]["adversarial"]
    typer.echo(f"Retrieval-only attack successes: {adv['attack_success_count']}. Wrote {out_dir / 'qa.json'}")


@app.command("report")
def run_report(
    eval_dir: Annotated[
        Path, typer.Option(help="Directory with backtest.json and coverage.json.")
    ] = EVAL_DIR,
    out: Annotated[Path, typer.Option(help="Markdown file to write.")] = DOC_PATH,
) -> None:
    """Regenerate docs/EVALUATION.md from the JSON files; no number is typed by hand."""
    backtest_result = _read_json(eval_dir / "backtest.json")
    coverage_result = _read_json(eval_dir / "coverage.json")
    from veedor.evaluation.qa.render import qa_block_of

    previous = qa_block_of(out.read_text(encoding="utf-8")) if out.is_file() else None
    text = report.render(backtest_result, coverage_result)
    if previous:  # the generated QA section belongs to `veedor evaluate qa`: keep it
        text = text.rstrip("\n") + "\n\n## Question answering (generated)\n\n" + previous + "\n"
    out.write_text(text, encoding="utf-8")
    typer.echo(f"Wrote {out}")


VALIDATION_DOC = REPO_ROOT / "docs" / "VALIDATION.md"


@app.command("validation")
def run_validation(
    n_boot: Annotated[int, typer.Option(min=100, help="Bootstrap replicates (medians).")] = 1000,
    seed: Annotated[int, typer.Option(help="Random seed.")] = 20260101,
    out_dir: Annotated[Path, typer.Option(help="Directory for eval/validation.json.")] = EVAL_DIR,
    doc: Annotated[Path, typer.Option(help="Markdown file with the results block.")] = VALIDATION_DOC,
) -> None:
    """Price validation and threshold bunching; writes eval/validation.json."""
    from veedor.evaluation import threshold_bunching, validation, validation_report

    settings = get_settings()
    try:
        result = validation.run_validation(
            settings.lake_dir, settings.marts_dir, out_dir / "backtest.json", doc, n_boot, seed
        )
        result["thresholds"] = threshold_bunching.run_bunching(settings.lake_dir, seed)
    except (FileNotFoundError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    _write_json(out_dir / "validation.json", result)
    block = validation_report.render_markdown(result)
    block += threshold_bunching.render_markdown(result["thresholds"])
    validation_report.update_doc(doc, block)
    typer.echo(f"Wrote {out_dir / 'validation.json'} and the results block of {doc}")
