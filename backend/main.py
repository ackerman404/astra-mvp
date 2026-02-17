"""Astra Proxy — FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.config import settings
from backend.database import create_db_and_tables


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown hooks."""
    # Startup: create database tables
    create_db_and_tables()

    # Store settings on app state for access in endpoints
    app.state.settings = settings

    # Create shared AsyncOpenAI client (used by proxy layer in Plan 09-02)
    if settings.OPENAI_API_KEY:
        from openai import AsyncOpenAI

        app.state.openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    else:
        app.state.openai_client = None

    yield

    # Shutdown: close OpenAI client if it was created
    if app.state.openai_client is not None:
        await app.state.openai_client.close()


app = FastAPI(
    title="Astra Proxy",
    version="3.0.0",
    lifespan=lifespan,
)
