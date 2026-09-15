"""Analysis-facing acquisition guard.

Collection-window provenance intentionally lives separately from raw reviews.
If the user deletes all local rows for a game, an older coverage record must
never turn into a false cache hit.  Manual collection is always force-fresh;
this guard protects the automatic Analyze path.
"""
from __future__ import annotations

from typing import Callable, Optional

from . import storage
from .acquisition import AcquisitionResult, collect_reviews, ensure_reviews as _ensure_reviews
from .sampling import SamplingContract


def ensure_reviews(
    contract: SamplingContract,
    *,
    progress_callback: Optional[Callable[[int], None]] = None,
) -> AcquisitionResult:
    if storage.count_reviews(contract.app_id) == 0:
        return collect_reviews(contract, force=True, progress_callback=progress_callback)
    return _ensure_reviews(contract, progress_callback=progress_callback)


__all__ = ["ensure_reviews"]
