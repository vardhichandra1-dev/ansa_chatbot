from __future__ import annotations

import json
import uuid
from pathlib import Path

import aiofiles
from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.resume import Resume
from app.models.user import User
from app.services.vector_store_service import VectorStoreService


async def save_resume(
    file: UploadFile,
    user: User,
    db: AsyncSession,
    vector_store: VectorStoreService,
) -> Resume:
    if file.content_type not in (
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/plain",
    ):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only PDF, DOCX, and TXT files are supported",
        )

    content = await file.read()
    size_mb = len(content) / (1024 * 1024)
    if size_mb > settings.max_upload_size_mb:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {settings.max_upload_size_mb} MB limit",
        )

    user_dir = settings.upload_path / str(user.id) / "resumes"
    user_dir.mkdir(parents=True, exist_ok=True)
    file_path = user_dir / f"{uuid.uuid4()}_{file.filename}"

    async with aiofiles.open(file_path, "wb") as f:
        await f.write(content)

    parsed = _parse_file(file_path, file.content_type or "")
    skills, experience, education = _extract_sections(parsed)

    resume = Resume(
        user_id=user.id,
        filename=file.filename or "resume",
        file_path=str(file_path),
        parsed_text=parsed,
        skills=json.dumps(skills),
        experience=json.dumps(experience),
        education=json.dumps(education),
    )
    db.add(resume)
    await db.flush()

    doc_id = await vector_store.add_resume(
        resume_id=str(resume.id),
        user_id=str(user.id),
        text=parsed,
        metadata={"skills": skills, "filename": file.filename},
    )
    resume.chroma_doc_id = doc_id
    await db.flush()

    # Mark as primary if it's the first resume
    result = await db.execute(
        select(Resume).where(Resume.user_id == user.id, Resume.id != resume.id)
    )
    if not result.scalars().first():
        resume.is_primary = True

    return resume


def _parse_file(path: Path, content_type: str) -> str:
    try:
        if content_type == "application/pdf" or str(path).endswith(".pdf"):
            import pdfplumber

            with pdfplumber.open(path) as pdf:
                return "\n".join(page.extract_text() or "" for page in pdf.pages)
        elif "wordprocessingml" in content_type or str(path).endswith(".docx"):
            from docx import Document

            doc = Document(str(path))
            return "\n".join(para.text for para in doc.paragraphs)
        else:
            return path.read_text(encoding="utf-8")
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Could not parse resume: {exc}",
        ) from exc


def _extract_sections(text: str) -> tuple[list[str], list[dict], list[dict]]:
    """Simple section extractor — production version would use an LLM."""
    lines = text.lower()
    skills: list[str] = []
    experience: list[dict] = []
    education: list[dict] = []

    skill_keywords = [
        "python", "fastapi", "langchain", "langgraph", "rag", "llm", "openai",
        "anthropic", "pytorch", "tensorflow", "react", "typescript", "postgresql",
        "redis", "docker", "kubernetes", "aws", "gcp", "azure", "git",
        "vector database", "chroma", "pinecone", "whisper", "transformers",
    ]
    for kw in skill_keywords:
        if kw in lines:
            skills.append(kw)

    return skills, experience, education


async def get_user_resumes(user: User, db: AsyncSession) -> list[Resume]:
    result = await db.execute(
        select(Resume).where(Resume.user_id == user.id).order_by(Resume.created_at.desc())
    )
    return list(result.scalars().all())


async def delete_resume(resume_id: uuid.UUID, user: User, db: AsyncSession) -> None:
    result = await db.execute(
        select(Resume).where(Resume.id == resume_id, Resume.user_id == user.id)
    )
    resume = result.scalar_one_or_none()
    if not resume:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found")
    try:
        Path(resume.file_path).unlink(missing_ok=True)
    except OSError:
        pass
    await db.delete(resume)
