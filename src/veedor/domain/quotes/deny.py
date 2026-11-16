"""Explicit deny list of passages, keyed by a hash of the passage (never by a name).

The screens of `domain.quotes.screen` are heuristics. When a human review of the stored quotes finds a passage
that names a person who is not a party of the process and no pattern catches it without removing legitimate
text, the passage goes here: its SHA-256 over `passage_key` (case and whitespace folded). The list holds no
name, so it can be published; the passage itself stays in the unmasked texts table, which is never published.

To add an entry: compute ``passage_hash(text)`` of the whole passage as extracted, append the hex digest
with a short comment saying only the *kind* of reason (for example "shareholder list"), then rebuild the
mart (`veedor quotes build`). `check_passage` applies the list both when the mart is built and when the API
serves a stored quote.
"""

from __future__ import annotations

import hashlib


def passage_key(text: str) -> str:
    """Identity of a passage: case and whitespace folded (also used to detect repeated passages)."""
    return " ".join(text.casefold().split())


def passage_hash(text: str) -> str:
    return hashlib.sha256(passage_key(text).encode("utf-8")).hexdigest()


# Entries: sha256 of `passage_key`. The comment names the kind of reason, never a person.
DENIED_PASSAGE_HASHES: frozenset[str] = frozenset(
    {
        "4969fbf08f26a9a0f1f8c62e6e997af6d2bf5b1eeaa3d17d14e389906c212a1b",  # list of shareholders by name
        "66f71a68364e75d47c603d3d942e4c272ed24db5646f29a84b104ae47b589a25",  # administrators named
        "b6d74f0f2b04651d13141f52a7b624ebd06f9d8d51288fdd549fe5856b041f41",  # official in an address block
        "17bc1ef70d8944b58b958b2ec85d510e101b8f1987605f6fc518e90fdcd0b302",  # trainer named in a letter
    }
)


def is_denied(text: str) -> bool:
    return passage_hash(text) in DENIED_PASSAGE_HASHES
