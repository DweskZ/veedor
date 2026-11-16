"""Version of everything that decides what a dossier says (templates, wording, masking, verifier).

Bump it whenever a change would alter the text of an already cached dossier: cached entries with a
different version are ignored and rebuilt.
"""

RENDERER_VERSION = 5
