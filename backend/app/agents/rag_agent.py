from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.base import get_llm
from app.services.vector_store_service import VectorStoreService

GUIDANCE_SYSTEM_PROMPT = """You are an expert technical interview coach.

Given a candidate's resume context and an interview question, generate personalized answer guidance.

Your response should:
1. Highlight relevant experience from the resume
2. Provide a structured answer framework (STAR for behavioral, technical breakdown for technical)
3. Mention key concepts to cover
4. Suggest specific examples from their background
5. Warn about common mistakes to avoid

Be concise and actionable. Target length: 200-400 words."""

COMPANY_FAQ_PROMPT = """You are an expert at interview preparation for top tech companies.

Generate the top 10 most frequently asked interview questions for:
Company: {company}
Role: {role}

Include a mix of:
- Technical questions relevant to the role
- Behavioral/culture questions
- System design questions (if applicable)

Return as a JSON array of question strings only. No markdown."""

SKILL_GAP_PROMPT = """You are a technical career coach.

Given a candidate's skills and a target role, analyze the skill gap.

Return JSON:
{{
  "strong_skills": ["skill1", "skill2"],
  "gap_skills": ["skill3", "skill4"],
  "priority_skills": ["most important missing skill"],
  "estimated_prep_weeks": number,
  "summary": "Brief analysis"
}}"""

STUDY_PLAN_PROMPT = """Create a structured study plan for interview preparation.

Company: {company}
Role: {role}
Gap Skills: {gap_skills}
Available Weeks: {weeks}

Return a JSON array of weekly plans:
[
  {{
    "week": 1,
    "focus": "Topic name",
    "topics": ["subtopic1", "subtopic2"],
    "resources": ["resource1"],
    "practice_questions": 5
  }}
]"""


class RAGAgent:
    def __init__(self, vector_store: VectorStoreService) -> None:
        self.vector_store = vector_store

    async def generate_answer_guidance(
        self,
        question: str,
        user_id: str,
        conversation_context: str = "",
    ) -> str:
        resume_chunks = await self.vector_store.search_resume(user_id, question, n_results=3)
        similar_qs = await self.vector_store.search_similar_questions(user_id, question, n_results=3)

        resume_context = "\n---\n".join(resume_chunks) if resume_chunks else "No resume available."
        past_context = (
            "\n".join(f"- {q['text']}" for q in similar_qs)
            if similar_qs
            else "No similar past questions."
        )

        llm = get_llm(temperature=0.3)
        response = await llm.ainvoke(
            [
                SystemMessage(content=GUIDANCE_SYSTEM_PROMPT),
                HumanMessage(
                    content=(
                        f"Resume context:\n{resume_context}\n\n"
                        f"Similar past questions:\n{past_context}\n\n"
                        f"Recent conversation:\n{conversation_context}\n\n"
                        f"Interview question: {question}"
                    )
                ),
            ]
        )
        return response.content

    async def generate_company_faq(self, company: str, role: str) -> list[str]:
        import json

        llm = get_llm(temperature=0.4)
        response = await llm.ainvoke(
            [
                SystemMessage(
                    content=COMPANY_FAQ_PROMPT.format(company=company, role=role)
                ),
                HumanMessage(content="Generate the FAQ list now."),
            ]
        )
        try:
            return json.loads(response.content)
        except json.JSONDecodeError:
            return [line.strip("- ") for line in response.content.split("\n") if line.strip()]

    async def analyze_skill_gap(
        self, candidate_skills: list[str], company: str, role: str
    ) -> dict:
        import json

        llm = get_llm(temperature=0.2)
        response = await llm.ainvoke(
            [
                SystemMessage(content=SKILL_GAP_PROMPT),
                HumanMessage(
                    content=(
                        f"Candidate skills: {', '.join(candidate_skills)}\n"
                        f"Target company: {company}\n"
                        f"Target role: {role}"
                    )
                ),
            ]
        )
        try:
            return json.loads(response.content)
        except json.JSONDecodeError:
            return {"summary": response.content, "gap_skills": [], "strong_skills": candidate_skills}

    async def generate_study_plan(
        self, company: str, role: str, gap_skills: list[str], weeks: int = 4
    ) -> list[dict]:
        import json

        llm = get_llm(temperature=0.3)
        response = await llm.ainvoke(
            [
                SystemMessage(
                    content=STUDY_PLAN_PROMPT.format(
                        company=company,
                        role=role,
                        gap_skills=", ".join(gap_skills),
                        weeks=weeks,
                    )
                ),
                HumanMessage(content="Generate the study plan now."),
            ]
        )
        try:
            return json.loads(response.content)
        except json.JSONDecodeError:
            return []
