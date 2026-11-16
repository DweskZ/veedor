"""Optional live registry lookup through the EcuDataMCP server. Not wired: only the port exists.

Verified facts (README and docs/TOOLS.md of https://github.com/DweskZ/EcuDataMCP, read on the day of
writing): the server runs over stdio with ``uvx ecuador-mcp --transport stdio`` and exposes
``get_compania_info``, ``get_sri_ruc_info``, ``search_companias`` and ``get_financials``. The published
documentation gives neither parameter names nor result schemas for them, so a client written now would
guess at both. Until those are verified against a running server, `build_ecudata_client` returns
`NoOpRegistryLookup`, which always answers ``None`` ("no disponible"). Nothing in the dossier pipeline
calls a live lookup.
"""

from __future__ import annotations

from typing import Protocol


class RegistryLookupPort(Protocol):
    def lookup(self, ruc: str) -> dict[str, object] | None:
        """Live registry facts for a RUC, or ``None`` when unavailable. Must never raise."""
        ...


class NoOpRegistryLookup:
    def lookup(self, ruc: str) -> dict[str, object] | None:
        return None


def build_ecudata_client() -> RegistryLookupPort:
    return NoOpRegistryLookup()
