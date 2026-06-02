"""Profile router — configure the single user's personal details."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.profile import Profile

router = APIRouter(prefix="/profile", tags=["profile"])


class ProfileUpdate(BaseModel):
    name: str | None = None
    target_role: str | None = None
    target_company: str | None = None
    bio: str | None = None


class ProfileResponse(BaseModel):
    id: int
    name: str
    target_role: str | None
    target_company: str | None
    bio: str | None

    model_config = {"from_attributes": True}


@router.get("", response_model=ProfileResponse)
async def get_profile(db: AsyncSession = Depends(get_db)):
    profile = await _get_or_create(db)
    return profile


@router.put("", response_model=ProfileResponse)
async def update_profile(data: ProfileUpdate, db: AsyncSession = Depends(get_db)):
    profile = await _get_or_create(db)
    if data.name is not None:
        profile.name = data.name
    if data.target_role is not None:
        profile.target_role = data.target_role
    if data.target_company is not None:
        profile.target_company = data.target_company
    if data.bio is not None:
        profile.bio = data.bio
    return profile


async def _get_or_create(db: AsyncSession) -> Profile:
    result = await db.execute(select(Profile).where(Profile.id == 1))
    profile = result.scalar_one_or_none()
    if not profile:
        profile = Profile(id=1)
        db.add(profile)
        await db.flush()
    return profile
