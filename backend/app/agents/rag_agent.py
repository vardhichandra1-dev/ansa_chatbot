from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.base import get_llm
from app.services.vector_store_service import VectorStoreService

GUIDANCE_PROMPT = """You are an expert technical interview coach helping a candidate during a LIVE interview.

The candidate has a resume and you have access to relevant excerpts from it.
Generate real-time answer guidance for the interview question.

Your response must be:
1. CONCISE — candidate must read it in under 30 seconds
2. STRUCTURED — use bullet points
3. PERSONALIZED — reference their actual experience from the resume
4. ACTIONABLE — tell them what to say, not just what to know

Format:
**Key points to cover:**
- [concept 1]
- [concept 2]

**From your experience:**
- [specific project/experience to mention]

**Framework:** [STAR / technical breakdown / etc.]

**Watch out for:** [common mistake to avoid]"""

COMPANY_FAQ_PROMPT = """You are an expert at interview preparation for top tech companies.

Generate the top 10 most frequently asked interview questions for:
Company: {company}
Role: {role}

Return as a JSON array of question strings only. No markdown."""

SKILL_GAP_PROMPT = """You are a technical career coach.
Given a candidate's skills and a target role, analyze the skill gap.
Return JSON:
{{
  "strong_skills": ["skill1"],
  "gap_skills": ["skill2"],
  "priority_skills": ["most critical missing skill"],
  "estimated_prep_weeks": 4,
  "summary": "brief analysis"
}}"""

STUDY_PLAN_PROMPT = """Create a structured {weeks}-week study plan.
Company: {company} | Role: {role} | Gap Skills: {gap_skills}
Return JSON array: [{{"week":1,"focus":"Topic","topics":["subtopic"],"practice_questions":5}}]"""


class RAGAgent:
    def __init__(self, vector_store: VectorStoreService) -> None:
        self.vs = vector_store

    async def generate_answer_guidance(
        self,
        question: str,
        conversation_context: str = "",
    ) -> str:
        resume_chunks = await self.vs.search_resume(question, n_results=3)
        similar_qs = await self.vs.search_similar_questions(question, n_results=3)

        resume_ctx = "\n---\n".join(resume_chunks) if resume_chunks else "No resume uploaded yet."
        past_ctx = (
            "\n".join(f"- {q['text']}" for q in similar_qs)
            if similar_qs
            else "No past questions yet."
        )

        llm = get_llm(temperature=0.3)
        response = await llm.ainvoke([
            SystemMessage(content=GUIDANCE_PROMPT),
            HumanMessage(content=(
                f"Resume excerpts:\n{resume_ctx}\n\n"
                f"Similar past questions you've practiced:\n{past_ctx}\n\n"
                f"Recent conversation:\n{conversation_context}\n\n"
                f"Current interview question: {question}"
            )),
        ])
        return response.content

    async def generate_company_faq(self, company: str, role: str) -> list[str]:
        import json
        llm = get_llm(temperature=0.4)
        response = await llm.ainvoke([
            SystemMessage(content=COMPANY_FAQ_PROMPT.format(company=company, role=role)),
            HumanMessage(content="Generate the FAQ list."),
        ])
        try:
            return json.loads(response.content)
        except json.JSONDecodeError:
            return [line.strip("- ") for line in response.content.split("\n") if line.strip()]

    async def analyze_skill_gap(self, candidate_skills: list[str], company: str, role: str) -> dict:
        import json
        llm = get_llm(temperature=0.2)
        response = await llm.ainvoke([
            SystemMessage(content=SKILL_GAP_PROMPT),
            HumanMessage(content=f"Skills: {', '.join(candidate_skills)}\nCompany: {company}\nRole: {role}"),
        ])
        try:
            return json.loads(response.content)
        except json.JSONDecodeError:
            return {"summary": response.content, "gap_skills": [], "strong_skills": candidate_skills}

    async def generate_study_plan(self, company: str, role: str, gap_skills: list[str], weeks: int = 4) -> list[dict]:
        import json
        llm = get_llm(temperature=0.3)
        response = await llm.ainvoke([
            SystemMessage(content=STUDY_PLAN_PROMPT.format(
                weeks=weeks, company=company, role=role, gap_skills=", ".join(gap_skills)
            )),
            HumanMessage(content="Generate the study plan."),
        ])
        try:
            return json.loads(response.content)
        except json.JSONDecodeError:
            return []
