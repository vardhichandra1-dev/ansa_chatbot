from __future__ import annotations

from collections.abc import AsyncGenerator

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.base import get_llm
from app.services.vector_store_service import VectorStoreService

# Shorter prompt = faster time-to-first-token
GUIDANCE_PROMPT = """You are a live interview coach. Generate CONCISE answer guidance (readable in 20 seconds).

Format:
**Key points:** [3-4 bullets]
**From your experience:** [1-2 bullets referencing resume]
**Framework:** [STAR / technical steps / etc.]
**Avoid:** [one common mistake]"""

COMPANY_FAQ_PROMPT = """Top 10 interview questions for {company} {role}. JSON array of strings only."""

SKILL_GAP_PROMPT = 'Skill gap for {role} at {company}. Return JSON: {{"strong_skills":[],"gap_skills":[],"priority_skills":[],"estimated_prep_weeks":4,"summary":""}}'

STUDY_PLAN_PROMPT = '{weeks}-week study plan. Company:{company} Role:{role} Gaps:{gap_skills}. JSON array: [{{"week":1,"focus":"","topics":[],"practice_questions":5}}]'


class RAGAgent:
    def __init__(self, vector_store: VectorStoreService) -> None:
        self.vs = vector_store

    # ── Parallel context fetch ────────────────────────────────────────────────

    async def fetch_context(
        self, question: str
    ) -> tuple[list[str], list[dict]]:
        """
        Fetch resume chunks and similar past questions IN PARALLEL.
        Called by live_session before streaming guidance.
        """
        import asyncio
        resume_chunks, similar_qs = await asyncio.gather(
            self.vs.search_resume(question, n_results=3),
            self.vs.search_similar_questions(question, n_results=2),
        )
        return resume_chunks, similar_qs

    # ── Streaming guidance (primary path for live interview) ─────────────────

    async def stream_guidance(
        self,
        question: str,
        conversation_context: str = "",
        resume_chunks: list[str] | None = None,
        similar_qs: list[dict] | None = None,
    ) -> AsyncGenerator[str, None]:
        """
        Async generator — yields guidance tokens as Claude produces them.
        First token arrives in ~0.5s; caller streams each token to the WebSocket.
        """
        resume_ctx = "\n---\n".join(resume_chunks or []) or "No resume uploaded."
        past_ctx = (
            "\n".join(f"- {q['text']}" for q in (similar_qs or []))
            or "None."
        )

        llm = get_llm(temperature=0.3, streaming=True)
        async for chunk in llm.astream([
            SystemMessage(content=GUIDANCE_PROMPT),
            HumanMessage(content=(
                f"Resume excerpts:\n{resume_ctx}\n\n"
                f"Past similar questions:\n{past_ctx}\n\n"
                f"Recent conversation:\n{conversation_context}\n\n"
                f"Question: {question}"
            )),
        ]):
            if chunk.content:
                yield chunk.content

    # ── Non-streaming fallback (batch processing / company prep) ─────────────

    async def generate_answer_guidance(
        self,
        question: str,
        conversation_context: str = "",
    ) -> str:
        resume_chunks, similar_qs = await self.fetch_context(question)
        result = ""
        async for token in self.stream_guidance(question, conversation_context, resume_chunks, similar_qs):
            result += token
        return result

    # ── Company prep ─────────────────────────────────────────────────────────

    async def generate_company_faq(self, company: str, role: str) -> list[str]:
        import json
        llm = get_llm(temperature=0.4)
        r = await llm.ainvoke([
            SystemMessage(content=COMPANY_FAQ_PROMPT.format(company=company, role=role)),
            HumanMessage(content="Generate the list."),
        ])
        try:
            return json.loads(r.content)
        except json.JSONDecodeError:
            return [line.strip("- ") for line in r.content.split("\n") if line.strip()]

    async def analyze_skill_gap(self, candidate_skills: list[str], company: str, role: str) -> dict:
        import json
        llm = get_llm(temperature=0.2)
        r = await llm.ainvoke([
            SystemMessage(content=SKILL_GAP_PROMPT.format(company=company, role=role)),
            HumanMessage(content=f"Skills: {', '.join(candidate_skills)}"),
        ])
        try:
            return json.loads(r.content)
        except json.JSONDecodeError:
            return {"summary": r.content, "gap_skills": [], "strong_skills": candidate_skills}

    async def generate_study_plan(self, company: str, role: str, gap_skills: list[str], weeks: int = 4) -> list[dict]:
        import json
        llm = get_llm(temperature=0.3)
        r = await llm.ainvoke([
            SystemMessage(content=STUDY_PLAN_PROMPT.format(
                weeks=weeks, company=company, role=role, gap_skills=", ".join(gap_skills)
            )),
            HumanMessage(content="Generate."),
        ])
        try:
            return json.loads(r.content)
        except json.JSONDecodeError:
            return []
