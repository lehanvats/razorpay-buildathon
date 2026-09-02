"""FastAPI application entry point.

    uvicorn app.main:app --reload

The scheduler runs as a separate process (`python -m app.scheduler.poller`)
rather than as a background task here, so restarting the API never drops a
pending retry.
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import cases, webhooks
from app.config import settings

logging.basicConfig(level=logging.INFO)


def create_app() -> FastAPI:
    """Build the app: CORS for the Vite dev server, routers, health check.

    Router mounts:
        /api/webhooks   Razorpay ingress — the entry point of the whole system
        /api/cases      list, detail, timeline
        /api/dashboard  funnel, gross vs incremental
        /api/escalations human review queue
        /api/demo       seeder + customer simulator (demo_mode only)
    """
    app = FastAPI(
        title="Recoup",
        description="Payment-failure recovery agent. The LLM proposes; the "
        "policy gate is the sole path to any money action.",
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(webhooks.router)
    app.include_router(cases.router)
    # TODO(step-08): dashboard, escalations, demo routers.

    @app.get("/health", tags=["ops"])
    def health() -> dict[str, str]:
        """Liveness only — deliberately does not touch the database.

        A health check that fails on a database blip invites an orchestrator
        to restart a process that is fine, turning a transient outage into a
        restart loop.
        """
        return {"status": "ok"}

    return app


app = create_app()
