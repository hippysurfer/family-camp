"""Shared camp-name/output-folder naming for the CLI tools' --out-dir
convention: ``family_camp2-fetch`` writes its cached download JSON
directly into ``--out-dir`` as ``<camp_name>.json``; ``cli.py``'s
``solve``/``revalidate`` write everything else into a fresh
``<camp_name>_<run timestamp>`` subfolder of it, derived from the
``--data``/``--legacy-cache`` file's own name - so a camp's name only
ever needs to be decided once, at fetch time.
"""

from __future__ import annotations

import re
from datetime import datetime

__all__ = ["slugify", "run_folder_name"]

_RUN_TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S"


def slugify(name: str) -> str:
    """Filesystem-safe lowercase slug: runs of whitespace/punctuation
    collapse to a single underscore, e.g. "Willesley 2026" ->
    "willesley_2026". Never empty - falls back to "camp" for a name
    that's entirely punctuation/whitespace (or blank)."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", name.strip()).strip("_").lower()
    return slug or "camp"


def run_folder_name(camp_name: str, when: datetime) -> str:
    """E.g. ``slugify("Willesley 2026")`` + a run timestamp ->
    "willesley_2026_20260815_130300" - every run gets its own folder, so
    a later run never overwrites an earlier one's reports."""
    return f"{slugify(camp_name)}_{when.strftime(_RUN_TIMESTAMP_FORMAT)}"
