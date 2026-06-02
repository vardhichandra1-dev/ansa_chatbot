from app.models.analytics import CompanyPrep, TopicPerformance, UserAnalytics
from app.models.interview import Answer, Interview, InterviewQuestion, MockSession
from app.models.resume import Resume
from app.models.user import User

__all_models__ = [
    User,
    Resume,
    Interview,
    InterviewQuestion,
    Answer,
    MockSession,
    UserAnalytics,
    TopicPerformance,
    CompanyPrep,
]

__all__ = [
    "User",
    "Resume",
    "Interview",
    "InterviewQuestion",
    "Answer",
    "MockSession",
    "UserAnalytics",
    "TopicPerformance",
    "CompanyPrep",
    "__all_models__",
]
