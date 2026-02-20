"""
Pydantic schemas for Interview-related operations.
"""
from typing import Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum


class InterviewType(str, Enum):
    """Types of interviews."""
    PHONE_SCREEN = "phone_screen"
    TECHNICAL = "technical"
    SYSTEM_DESIGN = "system_design"
    BEHAVIORAL = "behavioral"
    HR = "hr"
    FINAL = "final"
    MIXED = "mixed"


class InterviewStatus(str, Enum):
    """Interview status."""
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    RESCHEDULED = "rescheduled"
    NO_SHOW = "no_show"


# Base schemas
class InterviewBase(BaseModel):
    """Base interview schema."""
    title: str = Field(..., min_length=3, max_length=200)
    position: str = Field(..., min_length=2, max_length=100)
    interview_type: InterviewType
    description: Optional[str] = None
    duration_minutes: int = Field(default=60, ge=15, le=240)
    scheduled_at: datetime
    candidate_id: str
    interviewer_id: str
    recording_enabled: bool = True
    code_editor_enabled: bool = False
    whiteboard_enabled: bool = False
    programming_languages: list[str] = []


class InterviewCreate(InterviewBase):
    """Schema for creating an interview."""
    company_id: str
    round_number: int = 1
    evaluation_criteria: Optional[Dict[str, Any]] = None


class InterviewUpdate(BaseModel):
    """Schema for updating an interview."""
    title: Optional[str] = Field(None, min_length=3, max_length=200)
    description: Optional[str] = None
    duration_minutes: Optional[int] = Field(None, ge=15, le=240)
    scheduled_at: Optional[datetime] = None
    interviewer_id: Optional[str] = None
    status: Optional[InterviewStatus] = None
    recording_enabled: Optional[bool] = None
    code_editor_enabled: Optional[bool] = None
    whiteboard_enabled: Optional[bool] = None


class InterviewInDB(InterviewBase):
    """Schema for interview in database."""
    id: str
    company_id: str
    status: InterviewStatus
    round_number: int
    meeting_url: str
    room_id: str
    recording_url: Optional[str] = None
    code_snapshot_id: Optional[str] = None
    whiteboard_snapshot_id: Optional[str] = None
    evaluation_id: Optional[str] = None
    actual_start_time: Optional[datetime] = None
    actual_end_time: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class InterviewResponse(BaseModel):
    """Schema for interview in API responses."""
    id: str
    title: str
    position: str
    interview_type: InterviewType
    status: InterviewStatus
    duration_minutes: int
    scheduled_at: datetime
    candidate_id: str
    interviewer_id: str
    meeting_url: str
    room_id: str
    recording_enabled: bool
    code_editor_enabled: bool
    whiteboard_enabled: bool
    programming_languages: list[str]
    created_at: datetime
    
    # Nested data
    candidate: Optional[Dict[str, Any]] = None
    interviewer: Optional[Dict[str, Any]] = None
    evaluation: Optional[Dict[str, Any]] = None
    
    class Config:
        from_attributes = True


class InterviewListResponse(BaseModel):
    """Schema for paginated interview list."""
    items: list[InterviewResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# Reschedule schemas
class InterviewRescheduleRequest(BaseModel):
    """Schema for requesting interview reschedule."""
    interview_id: str
    reason: str = Field(..., min_length=10, max_length=500)
    proposed_times: list[datetime] = Field(..., min_items=1, max_items=5)


class InterviewRescheduleResponse(BaseModel):
    """Schema for reschedule response."""
    id: str
    interview_id: str
    requested_by: str
    reason: str
    proposed_times: list[datetime]
    status: str
    created_at: datetime


# Bulk scheduling schemas
class BulkInterviewCandidate(BaseModel):
    """Schema for candidate in bulk interview creation."""
    email: str
    full_name: str
    position: str
    resume_url: Optional[str] = None
    preferred_dates: Optional[list[str]] = None


class BulkInterviewCreate(BaseModel):
    """Schema for bulk interview creation."""
    company_id: str
    interview_type: InterviewType
    duration_minutes: int = 60
    date_range_start: datetime
    date_range_end: datetime
    interviewer_ids: list[str] = []
    auto_assign: bool = True
    candidates: list[BulkInterviewCandidate]
    code_editor_enabled: bool = False
    whiteboard_enabled: bool = False
    recording_enabled: bool = True


class BulkInterviewResponse(BaseModel):
    """Schema for bulk interview creation response."""
    total_candidates: int
    successfully_scheduled: int
    failed: int
    interviews: list[InterviewResponse]
    errors: list[Dict[str, Any]]
