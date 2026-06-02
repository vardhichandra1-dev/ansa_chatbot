from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.resume_service import delete_resume, get_resumes, save_resume
from app.services.vector_store_service import get_vector_store

router = APIRouter(prefix="/resumes", tags=["resumes"])


@router.post("", status_code=201)
async def upload_resume(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    vector_store = get_vector_store()
    resume = await save_resume(file, db, vector_store)
    return {
        "id": str(resume.id),
        "filename": resume.filename,
        "is_active": resume.is_active,
        "created_at": resume.created_at.isoformat(),
    }


@router.get("")
async def list_resumes(db: AsyncSession = Depends(get_db)):
    resumes = await get_resumes(db)
    return [
        {
            "id": str(r.id),
            "filename": r.filename,
            "is_active": r.is_active,
            "skills": r.skills,
            "created_at": r.created_at.isoformat(),
        }
        for r in resumes
    ]


@router.delete("/{resume_id}", status_code=204)
async def remove_resume(resume_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    await delete_resume(resume_id, db)
