"""Builds the FastAPI app: CORS for the web frontend, then every router under /api."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import generate, health, videos
from .settings import get_settings


def create_app() -> FastAPI:
    app = FastAPI(
        title="Animator API",
        description="Starts whiteboard video generation for the web app. Accounts and videos live in Supabase.",
        version="1.0.0",
        docs_url="/api/docs",
        redoc_url=None,
        swagger_ui_oauth2_redirect_url="/api/docs/oauth2-redirect",
        openapi_url="/api/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().allowed_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )
    for router in (health.router, generate.router, videos.router):
        app.include_router(router, prefix="/api")
    return app
