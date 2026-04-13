"""Admin endpoints for license key management and dashboard."""

import hmac
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Query
from pydantic import BaseModel
from sqlmodel import Session, select, func, col

from backend.config import settings
from backend.database import get_session
from backend.models import LicenseKey, UsageLog

router = APIRouter(prefix="/v1/admin", tags=["admin"])


# --- Auth dependency ---


def require_admin(x_admin_secret: str = Header(...)):
    """Verify the X-Admin-Secret header matches ADMIN_SECRET."""
    if not settings.ADMIN_SECRET:
        raise HTTPException(status_code=503, detail="ADMIN_SECRET not configured on server.")
    if not hmac.compare_digest(x_admin_secret, settings.ADMIN_SECRET):
        raise HTTPException(status_code=401, detail="Invalid admin secret.")


# --- Schemas ---


class CreateKeyRequest(BaseModel):
    tier: str = "standard"
    email: Optional[str] = None


class BulkCreateRequest(BaseModel):
    count: int = 1
    tier: str = "standard"
    email: Optional[str] = None


class CreateKeyResponse(BaseModel):
    license_key: str
    tier: str
    status: str


class BulkCreateResponse(BaseModel):
    keys: list[CreateKeyResponse]
    count: int


class KeyInfo(BaseModel):
    id: int
    key: str
    tier: str
    status: str
    email: Optional[str]
    hardware_id: Optional[str]
    created_at: datetime
    activated_at: Optional[datetime]
    expires_at: Optional[datetime]
    last_validated_at: Optional[datetime]


class KeyWithUsage(KeyInfo):
    """Key info with aggregated usage stats."""
    total_requests: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    last_request_at: Optional[datetime] = None


class RevokeResponse(BaseModel):
    revoked: bool


class DashboardSummary(BaseModel):
    """High-level stats for the admin dashboard."""
    total_keys: int
    active_keys: int
    unused_keys: int
    revoked_keys: int
    total_requests: int
    total_prompt_tokens: int
    total_completion_tokens: int


# --- Endpoints ---


@router.get("/summary", response_model=DashboardSummary, dependencies=[Depends(require_admin)])
async def get_dashboard_summary(session: Session = Depends(get_session)):
    """Get high-level dashboard stats."""
    all_keys = session.exec(select(LicenseKey)).all()

    active = sum(1 for k in all_keys if k.status == "active")
    unused = sum(1 for k in all_keys if k.status == "unused")
    revoked = sum(1 for k in all_keys if k.status == "revoked")

    # Aggregate usage
    usage_row = session.exec(
        select(
            func.count(UsageLog.id),
            func.coalesce(func.sum(UsageLog.prompt_tokens), 0),
            func.coalesce(func.sum(UsageLog.completion_tokens), 0),
        )
    ).one()

    return DashboardSummary(
        total_keys=len(all_keys),
        active_keys=active,
        unused_keys=unused,
        revoked_keys=revoked,
        total_requests=usage_row[0],
        total_prompt_tokens=usage_row[1],
        total_completion_tokens=usage_row[2],
    )


@router.post("/keys", response_model=CreateKeyResponse, dependencies=[Depends(require_admin)])
async def create_license_key(body: CreateKeyRequest, session: Session = Depends(get_session)):
    """Create a new license key."""
    key = str(uuid.uuid4())
    db_key = LicenseKey(key=key, tier=body.tier, status="unused", email=body.email)
    session.add(db_key)
    session.commit()
    return CreateKeyResponse(license_key=key, tier=db_key.tier, status=db_key.status)


@router.post("/keys/bulk", response_model=BulkCreateResponse, dependencies=[Depends(require_admin)])
async def bulk_create_keys(body: BulkCreateRequest, session: Session = Depends(get_session)):
    """Generate multiple license keys at once."""
    if body.count < 1 or body.count > 100:
        raise HTTPException(status_code=400, detail="Count must be between 1 and 100.")

    keys = []
    for _ in range(body.count):
        key = str(uuid.uuid4())
        db_key = LicenseKey(key=key, tier=body.tier, status="unused", email=body.email)
        session.add(db_key)
        keys.append(CreateKeyResponse(license_key=key, tier=body.tier, status="unused"))
    session.commit()

    return BulkCreateResponse(keys=keys, count=len(keys))


@router.get("/keys", response_model=list[KeyWithUsage], dependencies=[Depends(require_admin)])
async def list_license_keys(
    status: Optional[str] = Query(None, description="Filter by status: unused, active, revoked"),
    email: Optional[str] = Query(None, description="Filter by email (partial match)"),
    tier: Optional[str] = Query(None, description="Filter by tier"),
    session: Session = Depends(get_session),
):
    """List all license keys with usage stats and optional filtering."""
    statement = select(LicenseKey)
    if status:
        statement = statement.where(LicenseKey.status == status)
    if tier:
        statement = statement.where(LicenseKey.tier == tier)
    if email:
        statement = statement.where(col(LicenseKey.email).contains(email))

    # Order: active first, then unused, then revoked; newest first within each group
    statement = statement.order_by(
        # Custom sort: active=0, unused=1, revoked=2
        LicenseKey.status != "active",
        LicenseKey.status != "unused",
        LicenseKey.created_at.desc(),
    )

    keys = session.exec(statement).all()

    # Batch-fetch usage stats for all keys
    key_ids = [k.id for k in keys]
    usage_stats = {}
    if key_ids:
        usage_rows = session.exec(
            select(
                UsageLog.license_key_id,
                func.count(UsageLog.id),
                func.coalesce(func.sum(UsageLog.prompt_tokens), 0),
                func.coalesce(func.sum(UsageLog.completion_tokens), 0),
                func.max(UsageLog.created_at),
            ).where(col(UsageLog.license_key_id).in_(key_ids))
            .group_by(UsageLog.license_key_id)
        ).all()
        for row in usage_rows:
            usage_stats[row[0]] = {
                "total_requests": row[1],
                "total_prompt_tokens": row[2],
                "total_completion_tokens": row[3],
                "last_request_at": row[4],
            }

    result = []
    for k in keys:
        stats = usage_stats.get(k.id, {})
        result.append(KeyWithUsage(
            id=k.id, key=k.key, tier=k.tier, status=k.status,
            email=k.email, hardware_id=k.hardware_id,
            created_at=k.created_at, activated_at=k.activated_at,
            expires_at=k.expires_at, last_validated_at=k.last_validated_at,
            total_requests=stats.get("total_requests", 0),
            total_prompt_tokens=stats.get("total_prompt_tokens", 0),
            total_completion_tokens=stats.get("total_completion_tokens", 0),
            last_request_at=stats.get("last_request_at"),
        ))

    return result


@router.get("/keys/{key_id}/usage", dependencies=[Depends(require_admin)])
async def get_key_usage(key_id: int, session: Session = Depends(get_session)):
    """Get detailed usage history for a specific key."""
    db_key = session.get(LicenseKey, key_id)
    if db_key is None:
        raise HTTPException(status_code=404, detail="Key not found.")

    logs = session.exec(
        select(UsageLog)
        .where(UsageLog.license_key_id == key_id)
        .order_by(UsageLog.created_at.desc())
        .limit(100)
    ).all()

    return {
        "key_id": key_id,
        "key": db_key.key[:8] + "...",
        "status": db_key.status,
        "logs": [
            {
                "endpoint": log.endpoint,
                "model": log.model,
                "prompt_tokens": log.prompt_tokens,
                "completion_tokens": log.completion_tokens,
                "status_code": log.status_code,
                "latency_ms": round(log.latency_ms, 1),
                "created_at": log.created_at.isoformat(),
            }
            for log in logs
        ],
    }


@router.delete("/keys/{key_id}", response_model=RevokeResponse, dependencies=[Depends(require_admin)])
async def revoke_license_key(key_id: int, session: Session = Depends(get_session)):
    """Revoke a license key by ID."""
    db_key = session.get(LicenseKey, key_id)
    if db_key is None:
        raise HTTPException(status_code=404, detail="Key not found.")
    db_key.status = "revoked"
    db_key.hardware_id = None
    session.add(db_key)
    session.commit()
    return RevokeResponse(revoked=True)


@router.post("/keys/{key_id}/reset", response_model=KeyInfo, dependencies=[Depends(require_admin)])
async def reset_license_key(key_id: int, session: Session = Depends(get_session)):
    """Reset a key to unused (unbind from hardware, allow re-activation)."""
    db_key = session.get(LicenseKey, key_id)
    if db_key is None:
        raise HTTPException(status_code=404, detail="Key not found.")
    db_key.status = "unused"
    db_key.hardware_id = None
    session.add(db_key)
    session.commit()
    session.refresh(db_key)
    return KeyInfo(
        id=db_key.id, key=db_key.key, tier=db_key.tier, status=db_key.status,
        email=db_key.email, hardware_id=db_key.hardware_id,
        created_at=db_key.created_at, activated_at=db_key.activated_at,
        expires_at=db_key.expires_at, last_validated_at=db_key.last_validated_at,
    )
