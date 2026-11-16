"""What the question-answering route knows about one process: pack, fact sentences and stored quotes.

All three come from data the API already serves: the evidence pack (masked, as the dossier reads it), the
stored investigation of the process when the CLI made one, and the screened quotes of the mart. Nothing here
reads the unmasked texts table.
"""

from __future__ import annotations

from collections.abc import Callable

from veedor.domain.dossier.models import EvidencePack
from veedor.domain.qa.answer import QuotedPassage
from veedor.domain.qa.facts import build_facts
from veedor.use_cases.ask import ProcessContext, StoredQuote
from veedor.use_cases.queries._cache import VersionedCache
from veedor.use_cases.queries.ports import LakePort, NotFoundError
from veedor.use_cases.queries.quotes import get_process_quotes

PackLoader = Callable[[str], EvidencePack | None]
InvestigationFacts = Callable[[str], object | None]  # ocid -> InvestigationFacts | None


class ApiContextLoader:
    def __init__(self, lake: LakePort, load_pack: PackLoader, load_investigation: InvestigationFacts) -> None:
        self._lake = lake
        self._load_pack = load_pack
        self._load_investigation = load_investigation
        self._cache = VersionedCache(max_entries=256)

    def load(self, ocid: str) -> ProcessContext:
        """The pack and quotes are cached per data build; the stored investigation is read each time (it is a
        small file the CLI may have just written)."""
        pack, quotes = self._cache.get_or_compute(ocid, self._lake.data_version(), lambda: self._base(ocid))
        facts = self._load_investigation(ocid)
        if facts is not None:
            pack = pack.model_copy(update={"investigation": facts})
        return ProcessContext(pack, build_facts(pack), quotes, self._lake.data_version())

    def _base(self, ocid: str) -> tuple[EvidencePack, list[StoredQuote]]:
        pack = self._load_pack(ocid)
        if pack is None:
            raise NotFoundError("process", ocid)
        try:
            stored = get_process_quotes(self._lake, ocid)["items"]
        except Exception:  # noqa: BLE001 - quotes are optional context: without them the answer has none
            stored = []
        return pack, _quotes(stored)


def _quotes(items: list[dict]) -> list[StoredQuote]:
    out: list[StoredQuote] = []
    for rank, item in enumerate(items, 1):
        passages = [
            QuotedPassage(
                quote_id=f"q{rank}",
                text=item["text"],
                kind=item["kind"],
                date=item.get("date"),
                source_field=item["source_field"],
                truncated=bool(item.get("truncated")),
            )
        ]
        pair = item.get("pair")
        if pair:
            passages.append(
                QuotedPassage(
                    quote_id=f"q{rank}a",
                    text=pair["text"],
                    kind=pair["kind"],
                    date=None,
                    source_field=pair["source_field"],
                    truncated=bool(pair.get("truncated")),
                )
            )
        out.append(StoredQuote(rank, tuple(passages)))
    return out
