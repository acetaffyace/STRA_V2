"""FastAPI APIRouter modules for the SentiNext backend."""

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
