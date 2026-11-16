"""Store round-trip, privacy guard, service run with fakes, batch summary (counts only)."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fixtures" / "investigation"))
from fakes import TODAY, FakeBackend, ScriptedModel  # noqa: E402

from veedor.domain.dossier.models import EvidencePack  # noqa: E402
from veedor.infrastructure.investigations.store import InvestigationStore, PersonalDataError  # noqa: E402
from veedor.use_cases import investigate as use_case  # noqa: E402

PACKS = Path(__file__).resolve().parents[1] / "fixtures" / "dossier"
OCID = "ocds-5wno2w-TST-EC-SIE-2023-05-12345"


class NoLake:
    def buyer_key_index(self):
        return {}

    def pair_awards(self, args):
        return {"n_other_awards": 0, "n_with_amount": 0, "total_other_amount": None}

    def close(self):
        pass


def service(tmp_path, model=None, cap=None):
    pack = EvidencePack.model_validate(json.loads((PACKS / "pack_full.json").read_text()))
    return use_case.InvestigationService(
        loader=lambda ocid: pack if ocid == OCID else None,
        mcp=FakeBackend(), lake_tools=NoLake(), chat_model=model,
        store=InvestigationStore(tmp_path / "inv"), model_call_cap=cap, today=lambda: TODAY,
    )  # fmt: skip


def test_investigate_stores_a_record_that_round_trips(tmp_path):
    svc = service(tmp_path)
    record = svc.investigate(OCID)
    loaded = use_case.read_investigation(InvestigationStore(tmp_path / "inv"), OCID)
    assert loaded == record
    assert {r.specialist for r in record.specialists} == {"company", "tax_registry", "history", "audit"}
    assert record.tool_log and record.dossier.grounding_report.passed
    assert any(f.startswith("investigation.company") for f in record.facts_added)
    assert record.model_usage.calls == 0 and record.renderer_version >= 6
    assert all(c.started_at <= c.ended_at for c in record.tool_log)


def test_reading_never_runs_anything(tmp_path):
    assert use_case.read_investigation(InvestigationStore(tmp_path / "x"), OCID) is None
    (tmp_path / "x").mkdir()
    (tmp_path / "x" / f"{OCID}.json").write_text("{corrupt")
    assert use_case.read_investigation(InvestigationStore(tmp_path / "x"), OCID) is None


def test_store_rejects_bad_ocids_and_personal_ruc(tmp_path):
    store = InvestigationStore(tmp_path)
    for bad in ("", "a\x00b", "x" * 400, " padded "):
        with pytest.raises(ValueError):
            store.path(bad)
    for odd in ("../../etc/passwd", "a/b", ".hidden", "CCD\u2013GAD\u20132017", "Ñandú, 1"):
        assert store.path(odd).parent == tmp_path  # hashed name: nothing escapes the directory
    record = service(tmp_path).investigate(OCID)
    leaky = record.model_copy(update={"facts_added": ["1712345678001"]})
    with pytest.raises(PersonalDataError):
        InvestigationStore(tmp_path / "leak").save(leaky)


def test_batch_summary_has_counts_only_and_survives_errors(tmp_path):
    svc = service(tmp_path)
    errors = []
    summary, records = use_case.run_batch(svc, [OCID, "ocds-5wno2w-NOPE"], on_error=errors.append)
    data = summary.as_dict()
    assert data["investigations"] == 1 and data["errors"] == 1 and errors == ["ProcessNotFoundError"]
    assert data["dossiers_passing_verification"] == 1
    assert data["tool_calls_by_tool_and_outcome"]["get_compania_info"] == {"ok": 1}
    blob = json.dumps(data)
    assert OCID not in blob and "0992764473001" not in blob and "ocds-" not in blob
    path = tmp_path / "run.json"
    use_case.write_summary(path, {"no_llm": data})
    use_case.write_summary(path, {"with_llm": {"x": 1}})
    assert set(json.loads(path.read_text())) == {"no_llm", "with_llm"}


def test_model_calls_and_tokens_are_counted_and_capped(tmp_path):
    model = ScriptedModel(["not json"])
    svc = service(tmp_path, model=model, cap=3)
    record = svc.investigate(OCID)
    assert record.model_usage.calls == 3 and record.model_usage.prompt_tokens == 30
    assert record.dossier.grounding_report.passed


# --- review fixes: privacy guard, odd identifiers ----------------------------------------------


def test_float_artifacts_and_huge_tool_numbers_do_not_crash_or_withhold(tmp_path):
    """H1 shape: a ≥13-digit number in a tool result and float values in the grounding report."""
    from fakes import fixture

    financials = fixture("get_financials")
    financials["years"][0].update(activos=9.9e15, patrimonio=1234567890123.45)
    svc = use_case.InvestigationService(
        loader=lambda ocid: EvidencePack.model_validate(json.loads((PACKS / "pack_full.json").read_text())),
        mcp=FakeBackend({"get_financials": financials}), lake_tools=NoLake(), chat_model=None,
        store=InvestigationStore(tmp_path / "inv"), today=lambda: TODAY,
    )  # fmt: skip
    record = svc.investigate(OCID)
    assert record.withheld is None and record.dossier is not None and record.dossier.grounding_report.passed
    for token in record.dossier.grounding_report.supported:
        if token.kind in ("number", "percent"):
            assert token.matched is None or "." not in token.matched or len(token.matched.split(".")[-1]) <= 4


def test_a_genuine_privacy_hit_is_withheld_not_a_crash(tmp_path, monkeypatch):
    svc = service(tmp_path)
    calls = {"n": 0}

    def guard(text: str) -> bool:  # the first scan finds an identifier, as a genuine hit would
        calls["n"] += 1
        return calls["n"] == 1

    monkeypatch.setattr("veedor.infrastructure.investigations.store.contains_natural_person_ruc", guard)
    record = svc.investigate(OCID)
    assert record.withheld == "personal_data_guard" and record.dossier is None and record.facts_added == []
    stored = use_case.read_investigation(InvestigationStore(tmp_path / "inv"), OCID)
    assert stored is not None and stored.withheld == "personal_data_guard"
    assert (
        "1712345678001"
        not in (tmp_path / "inv" / next(p.name for p in (tmp_path / "inv").iterdir())).read_text()
    )
    summary = use_case.BatchSummary()
    summary.add(record)
    assert summary.as_dict()["withheld_by_privacy_guard"] == 1


def test_unusual_real_identifiers_are_stored_under_hashed_names_and_round_trip(tmp_path):
    odd = "ocds-5wno2w-CCD–GADPRP–002–2017-121382"
    pack = EvidencePack.model_validate(json.loads((PACKS / "pack_full.json").read_text()))
    pack = pack.model_copy(update={"process": pack.process.model_copy(update={"ocid": odd})})
    svc = use_case.InvestigationService(
        loader=lambda ocid: pack, mcp=FakeBackend(), lake_tools=NoLake(), chat_model=None,
        store=InvestigationStore(tmp_path / "inv"), today=lambda: TODAY,
    )  # fmt: skip
    record = svc.investigate(odd)
    store = InvestigationStore(tmp_path / "inv")
    assert store.load(odd) == record and store.ocids() == [odd]
    assert [p.suffix for p in (tmp_path / "inv").iterdir()] == [".json"]


def test_cli_rejects_odd_identifiers_with_a_clean_message(tmp_path):
    from typer.testing import CliRunner

    from veedor.cli.investigate import app

    runner = CliRunner()
    for bad in ("", "a\x00b", "x" * 400):
        result = runner.invoke(app, ["run", bad, "--no-llm", "--offline"])
        assert result.exit_code == 2 and "Traceback" not in result.output
    for odd in ("../../etc/passwd", "a'b", "ñandú", ";rm -rf", "ocds-5wno2w-CCD–GAD–2017"):
        result = runner.invoke(app, ["show", odd])
        assert result.exit_code == 1 and result.exception is None or isinstance(result.exception, SystemExit)
        assert "Traceback" not in result.output


def _batch_env(tmp_path, monkeypatch, recorded=20, run_size=2):
    """A CLI batch with the heavy parts faked; the 'default' summary file lives under tmp_path."""
    from contextlib import contextmanager

    from veedor.cli import investigate as cli

    (tmp_path / "eval").mkdir()
    default = tmp_path / "eval" / "investigations_run.json"
    default.write_text(json.dumps({"no_llm": {"investigations": recorded}}))
    monkeypatch.setattr(cli, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(cli, "_top_ocids", lambda n: [f"o{i}" for i in range(n)])
    started = {"n": 0}

    @contextmanager
    def backend(live=True):
        started["n"] += 1
        yield None

    class Service:
        def close(self):
            pass

    def run_batch(service, ocids, on_error=None):
        summary = use_case.BatchSummary()
        summary.investigations = run_size
        return summary, []

    monkeypatch.setattr(use_case, "live_backend", backend)
    monkeypatch.setattr(use_case, "build_service", lambda **kw: Service())
    monkeypatch.setattr(use_case, "run_batch", run_batch)
    return cli, default, started


def test_a_smaller_batch_never_replaces_a_larger_recorded_run(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    cli, default, started = _batch_env(tmp_path, monkeypatch)
    before = default.read_text()
    result = CliRunner().invoke(cli.app, ["batch", "--top", "3", "--no-llm"])
    assert result.exit_code == 2 and started["n"] == 0  # refused before any work
    assert default.read_text() == before


def test_a_batch_that_ends_smaller_than_the_record_does_not_write(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    cli, default, _ = _batch_env(tmp_path, monkeypatch, recorded=3, run_size=1)
    before = default.read_text()
    result = CliRunner().invoke(cli.app, ["batch", "--top", "3", "--no-llm"])
    assert result.exit_code == 2 and default.read_text() == before


def test_summary_out_and_force_are_explicit_ways_to_write(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    cli, default, _ = _batch_env(tmp_path, monkeypatch)
    before = default.read_text()
    other = tmp_path / "other" / "run.json"
    result = CliRunner().invoke(cli.app, ["batch", "--top", "3", "--no-llm", "--summary-out", str(other)])
    assert result.exit_code == 0 and json.loads(other.read_text())["no_llm"]["investigations"] == 2
    assert default.read_text() == before
    forced = CliRunner().invoke(cli.app, ["batch", "--top", "3", "--no-llm", "--force"])
    assert forced.exit_code == 0 and json.loads(default.read_text())["no_llm"]["investigations"] == 2


@pytest.mark.parametrize("spelling", ["1.710.034.065", "1710034065", "171-0034-065-001", "1710034065 001"])
def test_a_pack_value_holding_an_identifier_is_withheld_end_to_end(tmp_path, spelling):
    pack = EvidencePack.model_validate(json.loads((PACKS / "pack_full.json").read_text()))
    pack = pack.model_copy(
        update={"process": pack.process.model_copy(update={"buyer_name": f"HOSPITAL DE {spelling}"})}
    )
    svc = use_case.InvestigationService(
        loader=lambda ocid: pack, mcp=FakeBackend(), lake_tools=NoLake(), chat_model=None,
        store=InvestigationStore(tmp_path / "inv"), today=lambda: TODAY,
    )  # fmt: skip
    record = svc.investigate(OCID)
    assert record.withheld == "personal_data_guard" and record.dossier is None
    stored = (tmp_path / "inv").iterdir().__next__().read_text()
    # The old check looked for the bare fragment "034", which also occurs in the microseconds of a
    # timestamp (flaky). Look for the identifier in every shape it was written in instead: whole, digits
    # only, the buyer text around it, and the tail of the separated spellings (e.g. "034.065").
    digits = re.sub(r"\D", "", spelling)[:10]
    assert not any(token in stored for token in (spelling, digits, "HOSPITAL DE"))
    assert not re.search(r"0?34[\s.\-]+0?65", stored)
