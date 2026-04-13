"""Astra Proxy — FastAPI application entry point."""

import logging
import sys
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.config import settings
from backend.database import create_db_and_tables

logger = logging.getLogger("astra.server")

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)


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

        client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            timeout=httpx.Timeout(
                connect=5.0,
                read=60.0,
                write=10.0,
                pool=5.0,
            ),
        )
        app.state.openai_client = client

        # Startup validation (REL-05): verify OpenAI API key is valid
        try:
            await client.models.list()
            logger.info("OpenAI API key validated successfully")
        except Exception as exc:
            from openai import AuthenticationError

            if isinstance(exc, AuthenticationError):
                logger.critical(
                    "FATAL: OPENAI_API_KEY is invalid. Server refusing to start."
                )
                sys.exit(1)
            else:
                logger.warning(
                    "OpenAI unreachable during startup (may be temporary): %s", exc
                )
    else:
        app.state.openai_client = None
        logger.critical(
            "FATAL: OPENAI_API_KEY is missing. Server refusing to start."
        )
        sys.exit(1)

    yield

    # Shutdown: close OpenAI client if it was created
    if app.state.openai_client is not None:
        await app.state.openai_client.close()


app = FastAPI(
    title="Astra Proxy",
    version="3.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Global error handlers (REL-03)
# ---------------------------------------------------------------------------


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Return 400 with structured error for malformed requests."""
    return JSONResponse(
        status_code=400,
        content={
            "error": {
                "code": "invalid_request",
                "message": str(exc.errors()[0]["msg"]) if exc.errors() else "Invalid request.",
            }
        },
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Catch-all: never return stack traces to the client (REL-03)."""
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_error",
                "message": "Something went wrong. Please try again.",
            }
        },
    )


# ---------------------------------------------------------------------------
# Request logging middleware (REL-04)
# ---------------------------------------------------------------------------

from backend.middleware import RequestLoggingMiddleware  # noqa: E402

app.add_middleware(RequestLoggingMiddleware)


# ---------------------------------------------------------------------------
# Health check endpoint (REL-01)
# ---------------------------------------------------------------------------


@app.get("/health")
async def health_check(request: Request):
    """Health check — reports server status and OpenAI reachability."""
    result = {"status": "ok", "version": "3.0.0"}

    openai_client = request.app.state.openai_client
    if openai_client is not None:
        try:
            await openai_client.models.list()
            result["openai"] = "reachable"
        except Exception:
            result["openai"] = "unreachable"
    else:
        result["openai"] = "not_configured"

    return result


# ---------------------------------------------------------------------------
# Include routers
# ---------------------------------------------------------------------------

from backend.auth import router as license_router  # noqa: E402
from backend.proxy import router as proxy_router  # noqa: E402
from backend.admin import router as admin_router  # noqa: E402
from backend.dashboard import router as dashboard_router  # noqa: E402

app.include_router(license_router)
app.include_router(proxy_router)
app.include_router(admin_router)
app.include_router(dashboard_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)
