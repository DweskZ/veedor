"""The process identifier accepted in a URL path (pure).

An ocid is `ocds-5wno2w-<process code>`. Real codes are mostly `[A-Za-z0-9._-]`, but 891 of 2,251,027 contain
other characters because they were typed by hand (a space after a hyphen, an en dash, a comma, ``Ñ``...).
The pattern is a strict allow-list: letters, digits, the Latin letters ``ÑÇÓ`` that occur, and a short list of
punctuation (``. _ - , : + ( ) & º ° ·``, a space, and the dashes ``– — ‐ ‒ − －``). Never allowed:
control and
format characters (soft hyphen, zero-width, newlines), slashes and backslashes (a slash cannot travel inside
one path segment), quotes, ``%`` (so no percent-encoded traversal survives decoding),
``? # ; * ~ | ! < > { }``
and every other character. A code may not start with a space. The identifier is only ever used as a bound
query parameter, never to build SQL or a file name.
"""

from __future__ import annotations

import re

OCID_PREFIX = "ocds-5wno2w-"
_FIRST = r"A-Za-z0-9ÑÇÓ._\-,:+()&º°·–—‐‒−－"
_ALLOWED = _FIRST + " "
# No look-ahead (the validator of the API is a Rust regex): the first character may not be a space.
OCID_PATTERN = rf"^ocds-5wno2w-[{_FIRST}][{_ALLOWED}]{{0,119}}$"
_COMPILED = re.compile(OCID_PATTERN)


def is_openable(ocid: str) -> bool:
    """True when `GET /processes/{ocid}` accepts this identifier (the process page can be linked)."""
    return _COMPILED.fullmatch(ocid) is not None and "\n" not in ocid
