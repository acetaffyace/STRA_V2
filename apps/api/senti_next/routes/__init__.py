"""FastAPI APIRouter modules for the SentiNext backend."""

# Keep the stable deterministic Version Comparison core small. Runtime guards
# that depend on event/LLM persistence metadata are installed before the V3
# route imports the core symbols.
from .. import version_comparison as _version_comparison_core
from ..version_comparison_hardening import (
    cohort_overlap_report as _cohort_overlap_report,
    confounder_events as _confounder_events,
    event_is_usable as _event_is_usable,
    normalize_semantic_manifest as _normalize_semantic_manifest,
    semantic_comparison as _semantic_comparison,
)

_original_semantic_manifest_builder = _version_comparison_core.build_semantic_sample_manifest


def _hardened_semantic_manifest_builder(*args, **kwargs):
    return _normalize_semantic_manifest(_original_semantic_manifest_builder(*args, **kwargs))


_version_comparison_core.event_is_usable = _event_is_usable
_version_comparison_core.cohort_overlap_report = _cohort_overlap_report
_version_comparison_core.confounder_events = _confounder_events
_version_comparison_core.semantic_comparison = _semantic_comparison
_version_comparison_core.build_semantic_sample_manifest = _hardened_semantic_manifest_builder

from .analysis import router as analysis_router
from .acquisition import router as acquisition_router
from .games import router as games_router
from .reviews import router as reviews_router
from .chat import router as chat_router
from .cost import router as cost_router
from .settings import router as settings_router
from .misc import router as misc_router
from .runs import router as runs_router
from .presentation import router as presentation_router
from .version_comparison import router as version_comparison_router

all_routers = [
    analysis_router,
    acquisition_router,
    games_router,
    reviews_router,
    chat_router,
    cost_router,
    settings_router,
    misc_router,
    runs_router,
    presentation_router,
    version_comparison_router,
]
