"""Dashboard metrics.

    GET /api/dashboard   funnel, gross vs incremental, per-class, control panel

Serves DashboardMetrics in one response so the two headline counters can
never disagree by being fetched at different moments — a demo where gross
and incremental are computed from different snapshots is a demo that gets
questioned.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


# @router.get("", response_model=DashboardMetrics)
# def get_dashboard(db=Depends(get_db)):
#     raise NotImplementedError("step-08: dashboard")
