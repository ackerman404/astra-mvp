"""Astra Proxy — FastAPI application entry point."""

from contextlib import asynccontextmanager

import httpx
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

    # Create shared AsyncOpenAI client with explicit timeouts (PROXY-05)
    if settings.OPENAI_API_KEY:
        from openai import AsyncOpenAI

        app.state.openai_client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            timeout=httpx.Timeout(
                connect=5.0,
                read=60.0,
                write=10.0,
                pool=5.0,
            ),
        )
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

# Include routers
from backend.auth import router as license_router  # noqa: E402
from backend.proxy import router as proxy_router  # noqa: E402

app.include_router(license_router)
app.include_router(proxy_router)
