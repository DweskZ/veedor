import json
from pathlib import Path

import pytest

from veedor.domain.dossier.errors import ProcessNotFoundError
from veedor.domain.dossier.models import Dossier, EvidencePack
from veedor.infrastructure.llm.fake import FakeChatModel
from veedor.use_cases.build_dossier import DossierService

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "dossier"
OCID = "ocds-5wno2w-TST-EC-SIE-2023-05-12345"


class StubReader:
    def __init__(self):
        self.loads = 0

    def load(self, ocid):
        self.loads += 1
        if ocid != OCID:
            return None
        return EvidencePack.model_validate(json.loads((FIXTURES / "pack_full.json").read_text()))


def _service(tmp_path, reader, model=None):
    return DossierService(
        reader=reader,
        chat_model=model,
        dossiers_dir=tmp_path / "dossiers",
        traces_dir=tmp_path / "traces",
        config_dir=tmp_path / "config",
    )


def test_build_writes_cache_and_reuses_it(tmp_path):
    reader = StubReader()
    service = _service(tmp_path, reader)
    first = service.build(OCID)
    assert (tmp_path / "dossiers" / f"{OCID}.json").is_file()
    second = service.build(OCID)
    assert reader.loads == 1 and second == first
    service.build(OCID, refresh=True)
    assert reader.loads == 2
    assert isinstance(
        Dossier.model_validate_json((tmp_path / "dossiers" / f"{OCID}.json").read_text()), Dossier
    )


def test_corrupt_cache_is_rebuilt(tmp_path):
    service = _service(tmp_path, StubReader())
    path = tmp_path / "dossiers" / f"{OCID}.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not json")
    assert service.build(OCID).mode == "template"


@pytest.mark.parametrize("bad", ["../etc/passwd", "a/b", "", "x" * 300, ".hidden"])
def test_malformed_ocid_is_rejected_before_touching_disk(tmp_path, bad):
    with pytest.raises(ValueError):
        _service(tmp_path, StubReader()).build(bad)


def test_unknown_process_raises_and_caches_nothing(tmp_path):
    with pytest.raises(ProcessNotFoundError):
        _service(tmp_path, StubReader()).build("missing-ocid")
    assert not (tmp_path / "dossiers").exists()


def test_llm_failure_still_stores_a_verified_template_dossier(tmp_path):
    dossier = _service(tmp_path, StubReader(), FakeChatModel(["garbage"])).build(OCID)
    assert dossier.mode == "template" and dossier.grounding_report.passed


def test_template_only_service_does_not_serve_cached_llm_text(tmp_path):
    reader = StubReader()
    template_service = _service(tmp_path, reader)
    template_dossier = template_service.build(OCID)
    cache_path = tmp_path / "dossiers" / f"{OCID}.json"

    # Simulate a dossier written earlier with an LLM configured.
    cached_as_llm = template_dossier.model_copy(update={"mode": "llm"})
    cache_path.write_text(cached_as_llm.model_dump_json(), encoding="utf-8")

    rebuilt = template_service.build(OCID)

    assert rebuilt.mode == "template"
    assert reader.loads == 2
    assert Dossier.model_validate_json(cache_path.read_text()).mode == "template"


def test_cached_dossier_from_another_renderer_version_is_rebuilt(tmp_path):
    from veedor.domain.dossier.version import RENDERER_VERSION

    reader = StubReader()
    service = _service(tmp_path, reader)
    first = service.build(OCID)
    assert first.renderer_version == RENDERER_VERSION
    path = tmp_path / "dossiers" / f"{OCID}.json"
    stale = first.model_copy(update={"renderer_version": RENDERER_VERSION - 1, "summary_es": "texto antiguo"})
    path.write_text(stale.model_dump_json(), encoding="utf-8")
    rebuilt = service.build(OCID)
    assert reader.loads == 2 and rebuilt.summary_es != "texto antiguo"
    assert rebuilt.renderer_version == RENDERER_VERSION
    unversioned = json.loads(path.read_text())
    unversioned.pop("renderer_version")
    path.write_text(json.dumps(unversioned), encoding="utf-8")
    service.build(OCID)
    assert reader.loads == 3
    service.build(OCID)
    assert reader.loads == 3  # current entries are served from cache
