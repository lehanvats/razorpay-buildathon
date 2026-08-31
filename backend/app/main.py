"""FastAPI application entry point.

    uvicorn app.main:app --reload

The scheduler runs as a separate process (`python -m app.scheduler.poller`)
rather than as a background task here, so restarting the API never drops a
pending retry.
"""

from fastapi import FastAPI


def create_app() -> FastAPI:
    """Build the app: CORS for the Vite dev server, routers, health check.

    Router mounts:
        /api/webhooks   Razorpay ingress — the entry point of the whole system
        /api/cases      list, detail, timeline
        /api/dashboard  funnel, gross vs incremental
        /api/escalations human review queue
        /api/demo       seeder + customer simulator (demo_mode only)
    """
    raise NotImplementedError("step-01: app factory")


app = create_app()
