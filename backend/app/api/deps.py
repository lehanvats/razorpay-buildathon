"""Shared FastAPI dependencies.

Re-exports `get_db` and holds the demo-mode guard so routes stay thin.
"""

from app.db.session import get_db  # noqa: F401


def require_demo_mode() -> None:
    """Raise 404 unless `settings.demo_mode` is on.

    404 rather than 403 on purpose: a disabled demo surface should not
    advertise that it exists.
    """
    raise NotImplementedError("step-08: demo mode guard")
