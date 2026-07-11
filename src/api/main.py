"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.websocket import router as websocket_router
from src.config.settings import settings

app = FastAPI(
    title="EngageIQ AI",
    description="Agentic classroom engagement monitoring system",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# WebSocket endpoint for real-time frame streaming (Issue #5)
app.include_router(websocket_router)


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok", "version": "0.1.0"}


# TODO: Include route modules
# from src.api.routes import users, courses, sessions, engagement, reports
# app.include_router(users.router, prefix="/api")
# app.include_router(courses.router, prefix="/api")
