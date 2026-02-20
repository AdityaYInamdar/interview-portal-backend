"""
Test schemas for the testing platform
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator
from enum import Enum


class DifficultyLevel(str, Enum):
    easy = "easy"
    medium = "medium"
    hard = "hard"


class SessionStatus(str, Enum):
    not_started = "not_started"
    active = "active"
    paused = "paused"
    completed = "completed"
    expired = "expired"
    terminated = "terminated"


# ============================================
# Test Schemas
# ============================================

class TestBase(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    description: Optional[str] = None
    instructions: Optional[str] = None
    duration_minutes: int = Field(..., gt=0, le=480)
    passing_marks: int = Field(default=0, ge=0)
    is_published: bool = False
    is_active: bool = True


class TestCreate(TestBase):
    pass


class TestUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=3, max_length=200)
    description: Optional[str] = None
    instructions: Optional[str] = None
    duration_minutes: Optional[int] = Field(None, gt=0, le=480)
    passing_marks: Optional[int] = Field(None, ge=0)
    is_published: Optional[bool] = None
    is_active: Optional[bool] = None


class TestResponse(TestBase):
    id: str
    total_marks: int
    created_by: str
    company_id: str
    created_at: datetime
    updated_at: datetime
    published_at: Optional[datetime] = None
    question_count: Optional[int] = 0

    class Config:
        from_attributes = True


class TestWithQuestions(TestResponse):
    questions: List['QuestionInTest'] = []


# ============================================
# Test-Question Association
# ============================================

class TestQuestionAdd(BaseModel):
    question_id: str
    question_order: int = Field(..., ge=1)
    is_mandatory: bool = True


class TestQuestionBulkAdd(BaseModel):
    question_ids: List[str]
    is_mandatory: bool = True


class TestQuestionReorderItem(BaseModel):
    question_id: str
    question_order: int


class TestQuestionReorderPayload(BaseModel):
    questions: List[TestQuestionReorderItem]


class TestQuestionUpdate(BaseModel):
    question_order: Optional[int] = Field(None, ge=1)
    is_mandatory: Optional[bool] = None


class TestQuestionResponse(BaseModel):
    id: str
    test_id: str
    question_id: str
    question_order: int
    is_mandatory: bool
    created_at: datetime

    class Config:
        from_attributes = True


class QuestionInTest(BaseModel):
    id: str
    title: str
    question_type: str
    difficulty: str
    marks: int
    question_order: int
    is_mandatory: bool


# ============================================
# Test Invitation Schemas
# ============================================

class TestInvitationCreate(BaseModel):
    test_id: str
    candidate_email: str = Field(..., pattern=r'^[\w\.-]+@[\w\.-]+\.\w+$')
    candidate_name: str = Field(..., min_length=2, max_length=200)
    expires_in_hours: int = Field(default=72, gt=0, le=168)  # Max 7 days


class TestInvitationBulkCreate(BaseModel):
    test_id: str
    candidates: List[dict] = Field(..., min_length=1)  # [{email, name}, ...]
    expires_in_hours: int = Field(default=72, gt=0, le=168)


class TestInvitationResponse(BaseModel):
    id: str
    test_id: str
    candidate_email: str
    candidate_name: str
    invitation_token: str
    invitation_url: str
    expires_at: datetime
    is_used: bool
    sent_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True


# ============================================
# Test Session Schemas
# ============================================

class TestSessionStart(BaseModel):
    invitation_token: str


class TestSessionResponse(BaseModel):
    id: str
    invitation_id: str
    test_id: str
    candidate_email: str
    candidate_name: str
    session_token: str
    status: SessionStatus
    is_active: bool
    is_completed: bool
    is_expired: bool
    can_resume: bool
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    last_activity_at: Optional[datetime] = None
    expires_at: datetime
    time_remaining_seconds: Optional[int] = None
    ip_address: Optional[str] = None
    tab_switches: int = 0
    suspicious_activity_count: int = 0
    total_marks_obtained: float = 0
    total_marks: int = 0
    percentage_score: Optional[float] = None
    admin_reviewed: bool = False
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    admin_comments: Optional[str] = None
    final_status: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TestSessionWithTest(TestSessionResponse):
    test: TestResponse


class TestSessionAdminReview(BaseModel):
    admin_comments: Optional[str] = None
    final_status: str = Field(..., pattern='^(approved|rejected|pending)$')


class TestSessionResetRequest(BaseModel):
    reason: str = Field(..., min_length=10)


# ============================================
# Session Activity Logs
# ============================================

class SessionActivityCreate(BaseModel):
    activity_type: str = Field(..., max_length=100)
    activity_data: Optional[dict] = None


class SessionActivityResponse(BaseModel):
    id: str
    session_id: str
    activity_type: str
    activity_data: Optional[dict] = None
    timestamp: datetime

    class Config:
        from_attributes = True


# ============================================
# Statistics & Analytics
# ============================================

class TestStatistics(BaseModel):
    total_invitations: int
    total_attempts: int
    completed_attempts: int
    in_progress_attempts: int
    average_score: Optional[float] = None
    pass_rate: Optional[float] = None
    average_completion_time_minutes: Optional[float] = None


class CandidateTestStats(BaseModel):
    total_questions: int
    answered_questions: int
    correct_answers: int
    marks_obtained: float
    total_marks: int
    percentage: float
    time_spent_minutes: Optional[int] = None


# Forward reference resolution
TestWithQuestions.model_rebuild()
