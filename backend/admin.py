"""Admin endpoints for license key management."""

import hmac
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from sqlmodel import Session, select

from backend.config import settings
from backend.database import get_session
from backend.models import LicenseKey

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


class CreateKeyResponse(BaseModel):
    license_key: str
    tier: str
    status: str


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


class RevokeResponse(BaseModel):
    revoked: bool


# --- Endpoints ---


@router.post("/keys", response_model=CreateKeyResponse, dependencies=[Depends(require_admin)])
async def create_license_key(body: CreateKeyRequest, session: Session = Depends(get_session)):
    """Create a new license key."""
    key = str(uuid.uuid4())
    db_key = LicenseKey(key=key, tier=body.tier, status="unused", email=body.email)
    session.add(db_key)
    session.commit()
    return CreateKeyResponse(license_key=key, tier=db_key.tier, status=db_key.status)


@router.get("/keys", response_model=list[KeyInfo], dependencies=[Depends(require_admin)])
async def list_license_keys(session: Session = Depends(get_session)):
    """List all license keys."""
    keys = session.exec(select(LicenseKey)).all()
    return [KeyInfo(
        id=k.id, key=k.key, tier=k.tier, status=k.status,
        email=k.email, hardware_id=k.hardware_id,
        created_at=k.created_at, activated_at=k.activated_at,
        expires_at=k.expires_at,
    ) for k in keys]


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
        expires_at=db_key.expires_at,
    )
