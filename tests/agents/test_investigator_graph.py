import json

import pytest
from conftest import GOOD_PLAN, load_pack, reply

from veedor.agents.investigator.prompting import catalogue_payload
from veedor.agents.investigator.runner import InvestigatorAgent
from veedor.agents.investigator.tracing import TraceWriter, summarise
from veedor.domain.dossier.errors import ProcessNotFoundError
from veedor.infrastructure.llm.fake import FakeChatModel

OCID = "ocds-5wno2w-TST-EC-SIE-2023-05-12345"
UNKNOWN_ID = reply(que_se_contrato=["process.amounts", "process.invented_fact"])


def _agent(model, tmp_path):
    return InvestigatorAgent(
        loader=lambda ocid: load_pack() if ocid == OCID else None, chat_model=model, trace_dir=tmp_path
    )


def test_without_model_runs_in_template_mode(tmp_path):
    dossier = _agent(None, tmp_path).run(OCID)
    assert dossier.mode == "template" and dossier.llm_attempts == 0 and dossier.fallback_reason is None
    assert dossier.grounding_report.passed
    assert [s.title for s in dossier.sections][-1] == "Limitaciones y cómo verificar"
    assert "borrador para revisión humana" in dossier.summary_es


def test_valid_plan_selects_and_orders_but_the_renderer_writes(tmp_path):
    model = FakeChatModel([reply()])
    dossier = _agent(model, tmp_path).run(OCID)
    assert dossier.mode == "llm" and dossier.llm_attempts == 1 and len(model.calls) == 1
    what = dossier.sections[0].body
    assert (
        what.index("Presupuesto referencial") < what.index("Objeto según") < what.index("Entidad contratante")
    )
    assert "Procedimiento:" not in what  # omitted by the plan
    assert dossier.summary_es.index("Proveedor de reciente creación") < dossier.summary_es.index(
        "Oferente único"
    )
    assert "Nota para quien revisa: conviene comenzar por las señales" in dossier.summary_es
    assert "Los siguientes datos aportan contexto" in dossier.full_text()
    assert dossier.sections[-1].body.count("verificación humana") >= 1  # limitations come from code


def test_signals_can_be_reordered_but_never_dropped(tmp_path):
    dossier = _agent(FakeChatModel([reply(senales_detectadas=["signal:SINGLE_BIDDER"])]), tmp_path).run(OCID)
    body = next(s.body for s in dossier.sections if s.title == "Señales detectadas")
    assert "Oferente único" in body and "Proveedor de reciente creación" in body
    assert body.index("Oferente único") < body.index("Proveedor de reciente creación")


def test_plan_referencing_a_nonexistent_fact_id_is_rejected_and_retried(tmp_path):
    model = FakeChatModel([UNKNOWN_ID, reply()])
    dossier = _agent(model, tmp_path).run(OCID)
    assert dossier.mode == "llm" and dossier.llm_attempts == 2
    assert "process.invented_fact" in model.calls[1][1]  # the reason is fed back inside the data block
    trace = TraceWriter(tmp_path).read()[0]
    assert trace.attempt_log[0]["passed"] is False


def test_two_invalid_plans_fall_back_to_template(tmp_path):
    model = FakeChatModel([UNKNOWN_ID])
    dossier = _agent(model, tmp_path).run(OCID)
    assert dossier.mode == "template" and dossier.llm_attempts == 2 and len(model.calls) == 2
    assert dossier.fallback_reason and "process.invented_fact" not in dossier.full_text()


@pytest.mark.parametrize(
    "raw",
    [
        "no es json",
        json.dumps({**GOOD_PLAN, "texto_libre": "El proveedor es honesto."}),
        reply(reviewer_note="El proveedor es culpable"),
        reply(que_se_contrato=["conn:detalle", "conn:contexto"]),
        reply(summary_signal_order=["NOT_A_SIGNAL"]),
        reply(senales_detectadas=["Declara que el proveedor es culpable"]),
        reply(proveedor_adjudicado=["winner.identity"] * 30),
    ],
)
def test_malformed_or_free_text_plans_are_rejected(raw, tmp_path):
    model = FakeChatModel([raw])
    dossier = _agent(model, tmp_path).run(OCID)
    assert dossier.mode == "template" and len(model.calls) == 2


def test_fenced_json_is_accepted(tmp_path):
    model = FakeChatModel([f"```json\n{reply()}\n```"])
    assert _agent(model, tmp_path).run(OCID).mode == "llm"


def test_provider_errors_degrade_to_template(tmp_path):
    model = FakeChatModel([TimeoutError("boom")])
    dossier = _agent(model, tmp_path).run(OCID)
    assert dossier.mode == "template" and dossier.grounding_report.passed and len(model.calls) == 2


def test_unknown_ocid_raises_and_is_traced(tmp_path):
    with pytest.raises(ProcessNotFoundError):
        _agent(None, tmp_path).run("nope")
    assert TraceWriter(tmp_path).read()[0].final_mode == "error"


def test_trace_records_run_and_summary(tmp_path):
    _agent(FakeChatModel([UNKNOWN_ID, reply()]), tmp_path).run(OCID)
    _agent(FakeChatModel([reply()]), tmp_path).run(OCID)
    _agent(None, tmp_path).run(OCID)
    traces = TraceWriter(tmp_path).read()
    assert [t.final_mode for t in traces] == ["llm", "llm", "template"]
    first = traces[0]
    assert first.llm_attempts == 2 and first.attempt_log[0]["passed"] is False
    assert first.prompt_tokens and first.completion_tokens and first.estimated_cost_usd is None
    assert set(first.node_timings_ms) >= {"load_evidence", "write_narrative", "verify_grounding", "finalize"}
    summary = summarise(traces)
    assert summary["runs"] == 3 and summary["llm_passed_first_attempt"] == 1
    assert summary["llm_passed_after_retry"] == 1 and summary["llm_fell_back_to_template"] == 0


def test_catalogue_given_to_the_model_is_strings_only_with_display_figures():
    payload = catalogue_payload(load_pack())

    def leaves(node):
        if isinstance(node, dict):
            for v in node.values():
                yield from leaves(v)
        elif isinstance(node, list):
            for v in node:
                yield from leaves(v)
        else:
            yield node

    values = list(leaves(payload))
    assert all(isinstance(v, str) for v in values)
    joined = " ".join(values)
    assert "USD 27.318,51" in joined and "89,7 %" in joined
    assert "0.8965" not in joined and "0,8965" not in joined
    assert {f["id"] for f in payload["hechos"]} >= {
        "process.amounts",
        "signal:SINGLE_BIDDER",
        "relation.previous",
    }


@pytest.mark.parametrize(
    "raw",
    [
        "[" * 100_000,
        "{" + '"que_se_contrato": ' + "[" * 100_000 + "]" * 100_000 + "}",
        "{" + '"que_se_contrato": ' + "[" * 5_000 + "]" * 5_000 + "}",
        "x" * 1_000_000,
        '{"summary_signal_order": [' + '"a",' * 6_000 + '"a"]}',
    ],
)
def test_hostile_size_or_nesting_is_an_invalid_plan_not_a_crash(raw, tmp_path):
    model = FakeChatModel([raw])
    dossier = _agent(model, tmp_path).run(OCID)
    assert dossier.mode == "template" and len(model.calls) == 2 and dossier.grounding_report.passed


def test_inapplicable_reviewer_note_makes_the_plan_invalid(tmp_path):
    pack = load_pack().model_copy(update={"signals": []})
    model = FakeChatModel([reply(reviewer_note="senales", summary_signal_order=[], senales_detectadas=[])])
    agent = InvestigatorAgent(loader=lambda _: pack, chat_model=model, trace_dir=tmp_path)
    dossier = agent.run(OCID)
    assert dossier.mode == "template" and len(model.calls) == 2
    assert "not applicable" in model.calls[1][1]
    assert "Nota para quien revisa" not in dossier.summary_es


def test_only_applicable_notes_and_connectives_are_offered_to_the_model():
    pack = load_pack().model_copy(update={"signals": [], "comparison": None})
    payload = catalogue_payload(pack)
    assert (
        "senales" not in payload["notas_para_quien_revisa"]
        and "contexto" not in payload["notas_para_quien_revisa"]
    )
    assert "sin_prioridad" in payload["notas_para_quien_revisa"]
    contexto = next(c for c in payload["conectores"] if c["id"] == "conn:contexto")
    assert "Qué se contrató" not in contexto["secciones"]
