from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.base import get_llm


async def generate_weekly_report(
    user_data: dict,
    topic_performance: list[dict],
) -> dict:
    """Generate a weekly performance report with AI-powered insights."""
    llm = get_llm(temperature=0.3)
    response = await llm.ainvoke(
        [
            SystemMessage(
                content=(
                    "You are an interview preparation coach. "
                    "Analyze the candidate's weekly performance data and generate insights. "
                    "Return JSON with keys: "
                    '"recommendations" (list of strings), '
                    '"focus_areas" (list of strings), '
                    '"positive_trends" (list of strings), '
                    '"weekly_goal" (string).'
                )
            ),
            HumanMessage(
                content=(
                    f"Weekly stats:\n{json.dumps(user_data, indent=2)}\n\n"
                    f"Topic performance:\n{json.dumps(topic_performance, indent=2)}"
                )
            ),
        ]
    )
    try:
        return json.loads(response.content)
    except json.JSONDecodeError:
        return {
            "recommendations": [response.content],
            "focus_areas": [],
            "positive_trends": [],
            "weekly_goal": "Keep practicing!",
        }


async def identify_weak_areas(topic_performance: list[dict]) -> list[str]:
    """Return topics where the candidate needs the most improvement."""
    low_score_topics = [
        t["topic"]
        for t in topic_performance
        if t.get("avg_score") is not None and t["avg_score"] < 6.0
    ]
    unattempted = [
        t["topic"]
        for t in topic_performance
        if t.get("questions_attempted", 0) == 0
    ]
    return low_score_topics + unattempted


async def generate_preparation_plan(
    weak_areas: list[str],
    target_company: str | None,
    target_role: str | None,
    days_until_interview: int = 14,
) -> list[dict]:
    llm = get_llm(temperature=0.4)
    response = await llm.ainvoke(
        [
            SystemMessage(
                content=(
                    "You are an interview preparation strategist. "
                    "Create a day-by-day preparation plan. "
                    "Return a JSON array of daily tasks: "
                    '[{"day": 1, "focus": "Topic", "tasks": ["task1"], "duration_hours": 2}]'
                )
            ),
            HumanMessage(
                content=(
                    f"Weak areas: {', '.join(weak_areas)}\n"
                    f"Target company: {target_company or 'top tech company'}\n"
                    f"Target role: {target_role or 'Software Engineer'}\n"
                    f"Days available: {days_until_interview}"
                )
            ),
        ]
    )
    try:
        return json.loads(response.content)
    except json.JSONDecodeError:
        return []
