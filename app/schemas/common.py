"""
Pydantic schemas for Company and other entities.
"""
from typing import Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, HttpUrl
from enum import Enum


# ============ Company Schemas ============
class CompanyBase(BaseModel):
    """Base company schema."""
    name: str = Field(..., min_length=2, max_length=200)
    industry: Optional[str] = None
    company_size: Optional[str] = None
    website: Optional[HttpUrl] = None
    description: Optional[str] = None
    logo_url: Optional[str] = None


class CompanyCreate(CompanyBase):
    """Schema for creating a company."""
    admin_email: EmailStr
    admin_name: str
    admin_password: str = Field(..., min_length=8)


class CompanyUpdate(BaseModel):
    """Schema for updating company information."""
    name: Optional[str] = Field(None, min_length=2, max_length=200)
    industry: Optional[str] = None
    company_size: Optional[str] = None
    website: Optional[HttpUrl] = None
    description: Optional[str] = None
    logo_url: Optional[str] = None


class CompanyInDB(CompanyBase):
    """Schema for company in database."""
    id: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class CompanyResponse(CompanyBase):
    """Schema for company in API responses."""
    id: str
    created_at: datetime
    total_users: Optional[int] = 0
    total_interviews: Optional[int] = 0
    
    class Config:
        from_attributes = True


# ============ Code Execution Schemas ============
class CodeExecutionRequest(BaseModel):
    """Schema for code execution request."""
    language: str = Field(..., min_length=1, max_length=50)
    code: str = Field(..., min_length=1, max_length=50000)
    stdin: Optional[str] = ""
    args: Optional[list[str]] = []
    test_cases: Optional[list[Dict[str, str]]] = None


class CodeExecutionResult(BaseModel):
    """Schema for code execution result."""
    language: str
    version: str
    output: str
    stdout: str
    stderr: str
    exit_code: int
    execution_time: float
    memory_used: Optional[int] = None
    error: Optional[str] = None


class CodeSnapshot(BaseModel):
    """Schema for saving code snapshots during interview."""
    interview_id: str
    language: str
    code: str
    timestamp: datetime
    author_id: str


# ============ Whiteboard Schemas ============
class WhiteboardData(BaseModel):
    """Schema for whiteboard data."""
    interview_id: str
    data: Dict[str, Any]  # Canvas data
    timestamp: datetime
    author_id: str


class WhiteboardSnapshot(BaseModel):
    """Schema for whiteboard snapshot."""
    id: str
    interview_id: str
    data: Dict[str, Any]
    image_url: Optional[str] = None
    created_at: datetime


# ============ Recording Schemas ============
class RecordingStatus(str, Enum):
    """Recording status."""
    RECORDING = "recording"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class RecordingMetadata(BaseModel):
    """Schema for interview recording metadata."""
    interview_id: str
    status: RecordingStatus
    duration_seconds: Optional[int] = None
    file_size_bytes: Optional[int] = None
    video_url: Optional[str] = None
    started_at: datetime
    ended_at: Optional[datetime] = None


# ============ WebSocket Event Schemas ============
class WSEventType(str, Enum):
    """WebSocket event types."""
    # Connection events
    JOIN_ROOM = "join_room"
    LEAVE_ROOM = "leave_room"
    USER_JOINED = "user_joined"
    USER_LEFT = "user_left"
    
    # Code editor events
    CODE_CHANGE = "code_change"
    CODE_EXECUTION = "code_execution"
    CODE_EXECUTION_RESULT = "code_execution_result"
    CURSOR_POSITION = "cursor_position"
    
    # Whiteboard events
    WHITEBOARD_UPDATE = "whiteboard_update"
    WHITEBOARD_CLEAR = "whiteboard_clear"
    
    # Chat events
    CHAT_MESSAGE = "chat_message"
    
    # Video events
    WEBRTC_OFFER = "webrtc_offer"
    WEBRTC_ANSWER = "webrtc_answer"
    WEBRTC_ICE_CANDIDATE = "webrtc_ice_candidate"
    
    # Recording events
    START_RECORDING = "start_recording"
    STOP_RECORDING = "stop_recording"
    
    # Interview control
    INTERVIEW_START = "interview_start"
    INTERVIEW_END = "interview_end"


class WSMessage(BaseModel):
    """Base WebSocket message."""
    event: WSEventType
    room_id: str
    user_id: str
    data: Dict[str, Any]
    timestamp: Optional[datetime] = None


# ============ Analytics Schemas ============
class InterviewAnalytics(BaseModel):
    """Schema for interview analytics."""
    total_interviews: int
    completed_interviews: int
    upcoming_interviews: int
    cancelled_interviews: int
    average_duration_minutes: float
    completion_rate: float
    by_type: Dict[str, int]
    by_status: Dict[str, int]


class CandidateAnalytics(BaseModel):
    """Schema for candidate analytics."""
    total_candidates: int
    by_status: Dict[str, int]
    by_source: Dict[str, int]
    average_time_to_hire_days: Optional[float] = None
    conversion_rates: Dict[str, float]


class InterviewerAnalytics(BaseModel):
    """Schema for interviewer analytics."""
    interviewer_id: str
    total_interviews: int
    average_rating_given: float
    evaluation_completion_rate: float
    average_interview_duration: float
    on_time_percentage: float


# ============ Notification Schemas ============
class NotificationType(str, Enum):
    """Notification types."""
    INTERVIEW_SCHEDULED = "interview_scheduled"
    INTERVIEW_REMINDER = "interview_reminder"
    INTERVIEW_CANCELLED = "interview_cancelled"
    INTERVIEW_RESCHEDULED = "interview_rescheduled"
    EVALUATION_SUBMITTED = "evaluation_submitted"
    CANDIDATE_STATUS_UPDATED = "candidate_status_updated"


class NotificationCreate(BaseModel):
    """Schema for creating a notification."""
    user_id: str
    notification_type: NotificationType
    title: str
    message: str
    data: Optional[Dict[str, Any]] = None
    send_email: bool = True


class NotificationResponse(BaseModel):
    """Schema for notification in response."""
    id: str
    user_id: str
    notification_type: NotificationType
    title: str
    message: str
    data: Optional[Dict[str, Any]] = None
    is_read: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


# ============ File Upload Schemas ============
class FileUploadResponse(BaseModel):
    """Schema for file upload response."""
    file_url: str
    file_name: str
    file_size: int
    content_type: str
    bucket: str
