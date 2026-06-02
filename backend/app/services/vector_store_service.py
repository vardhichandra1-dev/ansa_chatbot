from __future__ import annotations

import uuid
from typing import Any

import chromadb
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

from app.config import settings


class VectorStoreService:
    """Thin wrapper around ChromaDB for development; swap for Pinecone in production."""

    def __init__(self) -> None:
        self._client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
        ef = OpenAIEmbeddingFunction(
            api_key=settings.openai_api_key,
            model_name="text-embedding-3-small",
        )
        self._resumes = self._client.get_or_create_collection("resumes", embedding_function=ef)
        self._questions = self._client.get_or_create_collection("questions", embedding_function=ef)
        self._knowledge = self._client.get_or_create_collection(
            "knowledge_base", embedding_function=ef
        )

    # ── Resume ──────────────────────────────────────────────────────────────────

    async def add_resume(
        self,
        resume_id: str,
        user_id: str,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        doc_id = str(uuid.uuid4())
        self._resumes.upsert(
            ids=[doc_id],
            documents=[text],
            metadatas=[{"resume_id": resume_id, "user_id": user_id, **(metadata or {})}],
        )
        return doc_id

    async def search_resume(self, user_id: str, query: str, n_results: int = 3) -> list[str]:
        results = self._resumes.query(
            query_texts=[query],
            n_results=n_results,
            where={"user_id": user_id},
        )
        return results["documents"][0] if results["documents"] else []

    # ── Questions ───────────────────────────────────────────────────────────────

    async def add_question(
        self,
        question_id: str,
        user_id: str,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        self._questions.upsert(
            ids=[question_id],
            documents=[text],
            metadatas=[{"user_id": user_id, **(metadata or {})}],
        )
        return question_id

    async def search_similar_questions(
        self, user_id: str, query: str, n_results: int = 5
    ) -> list[dict]:
        results = self._questions.query(
            query_texts=[query],
            n_results=n_results,
            where={"user_id": user_id},
        )
        if not results["documents"]:
            return []
        docs = results["documents"][0]
        metas = results["metadatas"][0] if results["metadatas"] else [{}] * len(docs)
        return [{"text": d, "metadata": m} for d, m in zip(docs, metas)]

    # ── Knowledge Base ───────────────────────────────────────────────────────────

    async def add_knowledge(
        self,
        doc_id: str,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._knowledge.upsert(
            ids=[doc_id],
            documents=[text],
            metadatas=[metadata or {}],
        )

    async def search_knowledge(self, query: str, n_results: int = 5) -> list[str]:
        results = self._knowledge.query(query_texts=[query], n_results=n_results)
        return results["documents"][0] if results["documents"] else []


_instance: VectorStoreService | None = None


def get_vector_store() -> VectorStoreService:
    global _instance
    if _instance is None:
        _instance = VectorStoreService()
    return _instance
