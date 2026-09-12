"""Read-only bridge to the production taxonomy and normalization semantics."""
from __future__ import annotations

import sys
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[3] / "apps" / "api"
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from senti_next import llm  # noqa: E402

TAXONOMY_VERSION = llm.TAXONOMY_VERSION
PROMPT_VERSION = llm.ACTIVE_PROMPT_VERSION
MAIN_CATEGORIES = frozenset(llm._ALLOWED_MAIN_CATEGORIES)
SUBCATEGORIES = {key: frozenset(value) for key, value in llm._ALLOWED_SUBCATEGORIES.items()}
SUBCATEGORY_KEYS = frozenset(llm._ALLOWED_SUBCATEGORY_KEYS)


def normalize_label(value: object) -> str | None:
    return llm._normalize_subcategory_value(value)


def valid_subcategory(value: object) -> bool:
    normalized = normalize_label(value)
    return normalized in SUBCATEGORY_KEYS if normalized else False


def taxonomy_manifest() -> dict:
    return {
        "taxonomy_version": TAXONOMY_VERSION,
        "prompt_version": PROMPT_VERSION,
        "main_categories": sorted(MAIN_CATEGORIES),
        "subcategories": {key: sorted(values) for key, values in sorted(SUBCATEGORIES.items())},
    }
