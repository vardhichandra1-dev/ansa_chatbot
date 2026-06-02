from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.base import get_llm
from app.schemas.interview import EvaluationResult

SYSTEM_PROMPT = """You are an expert technical interview evaluator.

Evaluate the candidate's answer to the interview question on a scale of 0-10 for each dimension:

1. technical_score: Accuracy and depth of technical knowledge
2. communication_score: Clarity, structure, and articulation
3. completeness_score: Coverage of key concepts and edge cases
4. confidence_score: Estimated confidence based on language patterns

Also provide:
- feedback: Constructive paragraph of feedback
- missing_concepts: Array of important concepts not covered
- strengths: Array of what was done well

Return JSON matching this exact schema:
{
  "technical_score": 0-10,
  "communication_score": 0-10,
  "completeness_score": 0-10,
  "confidence_score": 0-10,
  "feedback": "string",
  "missing_concepts": ["concept1", "concept2"],
  "strengths": ["strength1", "strength2"]
}

Return only valid JSON, no markdown."""

MOCK_QUESTION_PROMPT = """You are an expert technical interviewer at a top tech company.

Interview type: {interview_type}
Company: {company}
Role: {role}
Topics: {topics}
Conversation history length: {history_length} exchanges

Generate the next interview question. Consider:
- Start with warm-up, progress to harder questions
- Mix question types naturally
- Build on previous answers when appropriate

Return JSON:
{{
  "question": "The interview question",
  "type": "technical|behavioral|system_design|coding",
  "topic": "Topic name",
  "difficulty": "easy|medium|hard",
  "hint": "Optional hint to give if candidate is stuck"
}}"""


async def evaluate_answer(
    question: str,
    answer: str,
    question_type: str = "technical",
    expected_concepts: list[str] | None = None,
) -> EvaluationResult:
    context = ""
    if expected_concepts:
        context = f"\nExpected key concepts: {', '.join(expected_concepts)}"

    llm = get_llm(temperature=0.1)
    response = await llm.ainvoke(
        [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(
                content=(
                    f"Question type: {question_type}{context}\n\n"
                    f"Question: {question}\n\n"
                    f"Candidate's answer: {answer}"
                )
            ),
        ]
    )

    try:
        data = json.loads(response.content)
        return EvaluationResult(**data)
    except (json.JSONDecodeError, Exception):
        return EvaluationResult(
            technical_score=5.0,
            communication_score=5.0,
            completeness_score=5.0,
            confidence_score=5.0,
            feedback="Could not evaluate answer automatically.",
            missing_concepts=[],
            strengths=[],
        )


async def generate_mock_question(
    interview_type: str,
    company: str | None,
    role: str | None,
    topics: list[str],
    history_length: int,
) -> dict:
    llm = get_llm(temperature=0.7)
    response = await llm.ainvoke(
        [
            SystemMessage(
                content=MOCK_QUESTION_PROMPT.format(
                    interview_type=interview_type,
                    company=company or "a top tech company",
                    role=role or "Software Engineer",
                    topics=", ".join(topics) if topics else "General",
                    history_length=history_length,
                )
            ),
            HumanMessage(content="Generate the next interview question."),
        ]
    )

    try:
        return json.loads(response.content)
    except json.JSONDecodeError:
        return {
            "question": response.content.strip(),
            "type": interview_type,
            "topic": "General",
            "difficulty": "medium",
        }


async def generate_session_feedback(conversation: list[dict], scores: dict) -> str:
    """Generate an end-of-session summary with coaching feedback."""
    llm = get_llm(temperature=0.3)
    response = await llm.ainvoke(
        [
            SystemMessage(
                content=(
                    "You are an interview coach. Generate a comprehensive post-interview feedback "
                    "report. Cover: overall performance, key strengths, areas to improve, "
                    "specific topics to study, and actionable next steps. Be encouraging but honest."
                )
            ),
            HumanMessage(
                content=(
                    f"Session scores:\n{json.dumps(scores, indent=2)}\n\n"
                    f"Conversation summary ({len(conversation)} exchanges):\n"
                    + "\n".join(
                        f"[{m['role'].upper()}]: {m['content'][:200]}"
                        for m in conversation[-10:]
                    )
                )
            ),
        ]
    )
    return response.content
