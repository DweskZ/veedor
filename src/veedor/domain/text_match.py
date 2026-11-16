"""Accent- and case-insensitive name matching and ranking (pure, no I/O, no SQL)."""

from __future__ import annotations

import re
import unicodedata

_NON_ALNUM = re.compile(r"[^0-9a-z]+")

PREFIX, WORD_START, ALL_WORDS, SUBSTRING = range(4)


def fold(text: str) -> str:
    """Lower case, accents removed, every run of other characters collapsed to one space."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return _NON_ALNUM.sub(" ", stripped).strip()


def has_control_characters(text: str) -> bool:
    """True when any character is a control, format, surrogate, private-use or unassigned code point."""
    return any(unicodedata.category(ch).startswith("C") for ch in text)


def match_rank(folded_name: str, folded_query: str) -> int | None:
    """How well a folded name matches a folded query, or ``None``.

    0 the name starts with the query; 1 the query starts a word inside the name; 2 every query word
    starts some word of the name (any order); 3 the query appears inside a word.
    """
    if not folded_query:
        return None
    if folded_name.startswith(folded_query):
        return PREFIX
    if f" {folded_query}" in f" {folded_name}":
        return WORD_START
    words = folded_name.split()
    if all(any(word.startswith(token) for word in words) for token in folded_query.split()):
        return ALL_WORDS
    if folded_query in folded_name:
        return SUBSTRING
    return None
