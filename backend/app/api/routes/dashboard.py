"""Dashboard metrics.

    GET /api/dashboard   funnel, gross vs incremental, per-class, control panel

Serves DashboardMetrics in one response so the two headline counters can
never disagree by being fetched at different moments — a demo where gross
and incremental are computed from different snapshots is a demo that gets
questioned.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.api import DashboardMetrics
from app.services.metrics import compute_dashboard

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardMetrics)
def get_dashboard(db: Session = Depends(get_db)) -> DashboardMetrics:
    return compute_dashboard(db)
