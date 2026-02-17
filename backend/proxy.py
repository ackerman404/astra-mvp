"""Chat completions proxy — forwards LLM requests to OpenAI with SSE streaming."""

import asyncio
import logging
import time

import openai
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlmodel import Session

from backend.auth import validate_license
from backend.database import get_session
from backend.models import LicenseKey, UsageLog

logger = logging.getLogger("astra.proxy")

router = APIRouter(tags=["proxy"])


async def _log_usage(
    session_factory,
    license_key_id: int,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    status_code: int,
    latency_ms: float,
) -> None:
    """Fire-and-forget usage log insert."""
    try:
        from backend.database import engine
        from sqlmodel import Session as SyncSession

        with SyncSession(engine) as session:
            log = UsageLog(
                license_key_id=license_key_id,
                endpoint="chat/completions",
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                status_code=status_code,
                latency_ms=latency_ms,
            )
            session.add(log)
            session.commit()
    except Exception:
        logger.exception("Failed to log usage")


def _error_json(code: str, message: str) -> dict:
    """Build structured error response body."""
    return {"error": {"code": code, "message": message}}


@router.post("/v1/chat/completions")
async def proxy_chat_completions(
    request: Request,
    license_key: LicenseKey = Depends(validate_license),
):
    """Proxy chat completion requests to OpenAI with streaming support."""
    openai_client = request.app.state.openai_client
    if openai_client is None:
        return JSONResponse(
            status_code=502,
            content=_error_json("upstream_auth", "AI service configuration error. Contact support."),
        )

    # Parse request body as-is (pass through to OpenAI, no Pydantic model)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content=_error_json("invalid_request", "Request body must be valid JSON."),
        )

    # Model whitelist enforcement (PROXY-09)
    settings = request.app.state.settings
    model = body.get("model", "")
    if model not in settings.ALLOWED_MODELS:
        return JSONResponse(
            status_code=400,
            content=_error_json(
                "model_not_allowed",
                f"Model not permitted. Allowed: {', '.join(settings.ALLOWED_MODELS)}",
            ),
        )

    is_streaming = body.get("stream", False)
    start = time.monotonic()

    if is_streaming:
        return await _handle_streaming(request, openai_client, body, license_key, start)
    else:
        return await _handle_non_streaming(openai_client, body, license_key, start)


async def _handle_streaming(
    request: Request,
    client: openai.AsyncOpenAI,
    body: dict,
    license_key: LicenseKey,
    start: float,
):
    """Handle streaming chat completion with SSE forwarding."""
    # Ensure stream_options includes usage for token tracking (PROXY-08 / IG-01)
    body["stream"] = True
    body.setdefault("stream_options", {})
    body["stream_options"]["include_usage"] = True

    try:
        response = await _call_openai_with_retry(client, body)
    except openai.AuthenticationError:
        return JSONResponse(
            status_code=502,
            content=_error_json("upstream_auth", "AI service configuration error. Contact support."),
        )
    except openai.RateLimitError:
        return JSONResponse(
            status_code=429,
            content=_error_json("rate_limited", "Service is busy. Please wait a moment."),
        )
    except openai.APITimeoutError:
        return JSONResponse(
            status_code=504,
            content=_error_json("timeout", "Request timed out. Please try again."),
        )
    except openai.APIConnectionError:
        return JSONResponse(
            status_code=502,
            content=_error_json("upstream_unreachable", "Cannot reach AI service. Try again shortly."),
        )
    except openai.APIError:
        return JSONResponse(
            status_code=502,
            content=_error_json("upstream_error", "AI service temporarily unavailable."),
        )

    prompt_tokens = 0
    completion_tokens = 0

    async def stream_generator():
        nonlocal prompt_tokens, completion_tokens
        try:
            async for chunk in response:
                # Check if client disconnected
                if await request.is_disconnected():
                    break
                # Extract token usage from the final chunk
                if chunk.usage is not None:
                    prompt_tokens = chunk.usage.prompt_tokens
                    completion_tokens = chunk.usage.completion_tokens
                yield f"data: {chunk.model_dump_json()}\n\n"
            yield "data: [DONE]\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            # Fire-and-forget usage logging
            latency_ms = (time.monotonic() - start) * 1000
            asyncio.create_task(
                _log_usage(
                    None,
                    license_key.id,
                    body.get("model", "unknown"),
                    prompt_tokens,
                    completion_tokens,
                    200,
                    latency_ms,
                )
            )

    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _handle_non_streaming(
    client: openai.AsyncOpenAI,
    body: dict,
    license_key: LicenseKey,
    start: float,
):
    """Handle non-streaming chat completion."""
    body["stream"] = False

    try:
        response = await _call_openai_with_retry(client, body)
    except openai.AuthenticationError:
        return JSONResponse(
            status_code=502,
            content=_error_json("upstream_auth", "AI service configuration error. Contact support."),
        )
    except openai.RateLimitError:
        return JSONResponse(
            status_code=429,
            content=_error_json("rate_limited", "Service is busy. Please wait a moment."),
        )
    except openai.APITimeoutError:
        return JSONResponse(
            status_code=504,
            content=_error_json("timeout", "Request timed out. Please try again."),
        )
    except openai.APIConnectionError:
        return JSONResponse(
            status_code=502,
            content=_error_json("upstream_unreachable", "Cannot reach AI service. Try again shortly."),
        )
    except openai.APIError:
        return JSONResponse(
            status_code=502,
            content=_error_json("upstream_error", "AI service temporarily unavailable."),
        )

    latency_ms = (time.monotonic() - start) * 1000

    # Extract usage
    prompt_tokens = response.usage.prompt_tokens if response.usage else 0
    completion_tokens = response.usage.completion_tokens if response.usage else 0

    # Fire-and-forget usage logging
    asyncio.create_task(
        _log_usage(
            None,
            license_key.id,
            body.get("model", "unknown"),
            prompt_tokens,
            completion_tokens,
            200,
            latency_ms,
        )
    )

    return response.model_dump()


async def _call_openai_with_retry(client: openai.AsyncOpenAI, body: dict):
    """Call OpenAI with a single retry on 429/500 errors (PROXY-07)."""
    try:
        return await client.chat.completions.create(**body)
    except (openai.RateLimitError, openai.InternalServerError):
        # Wait 2 seconds and retry once
        await asyncio.sleep(2)
        return await client.chat.completions.create(**body)
