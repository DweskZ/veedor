import json
from pathlib import Path

import pytest

from veedor.domain.dossier.models import EvidencePack

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "dossier"


def load_pack(name: str = "pack_full", **process_updates) -> EvidencePack:
    pack = EvidencePack.model_validate(json.loads((FIXTURES / f"{name}.json").read_text()))
    if process_updates:
        pack = pack.model_copy(update={"process": pack.process.model_copy(update=process_updates)})
    return pack


GOOD_PLAN = {
    "summary_signal_order": ["NEW_SUPPLIER", "SINGLE_BIDDER"],
    "que_se_contrato": ["process.amounts", "process.object", "process.entity"],
    "senales_detectadas": ["signal:NEW_SUPPLIER", "signal:SINGLE_BIDDER"],
    "contexto_comparativo": ["conn:contexto", "context.median_ratio", "context.single_bidder_share"],
    "reviewer_note": "senales",
}


def reply(**overrides) -> str:
    return json.dumps({**GOOD_PLAN, **overrides}, ensure_ascii=False)


@pytest.fixture
def loader():
    packs = {}

    def load(ocid: str):
        return packs.get(ocid) or (load_pack() if ocid == "ocds-5wno2w-TST-EC-SIE-2023-05-12345" else None)

    load.packs = packs
    return load
