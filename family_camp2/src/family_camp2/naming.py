"""Shared camp-name/output-folder naming for the CLI's --out-dir
convention (REQUIREMENTS.md §4.12/§4.13): ``fetch`` writes its cached
download JSON directly into ``--out-dir`` as ``camp.json``; ``solve``/
``revalidate`` write everything else into a fresh
``<camp_name>_<run timestamp>`` subfolder of it.
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
