"""
Pydantic schemas for Candidate-related operations.
"""
from typing import Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field
from enum import Enum


class CandidateStatus(str, Enum):
    """Candidate status in hiring pipeline."""
    APPLIED = "applied"
    SCREENING = "screening"
    INTERVIEW_SCHEDULED = "interview_scheduled"
    INTERVIEWING = "interviewing"
    TECHNICAL_ROUND = "technical_round"
    FINAL_ROUND = "final_round"
    OFFER_EXTENDED = "offer_extended"
    HIRED = "hired"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    TALENT_POOL = "talent_pool"


class CandidateBase(BaseModel):
    """Base candidate schema."""
    email: EmailStr
    full_name: str = Field(..., min_length=2, max_length=100)
    phone: Optional[str] = None
    position_applied: str = Field(..., min_length=2, max_length=100)
    resume_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    github_url: Optional[str] = None
    portfolio_url: Optional[str] = None
    current_company: Optional[str] = None
    years_of_experience: Optional[int] = Field(None, ge=0, le=50)
    location: Optional[str] = None
    skills: list[str] = []
    education: Optional[str] = None


class CandidateCreate(CandidateBase):
    """Schema for creating a candidate."""
    company_id: Optional[str] = None
    source: Optional[str] = "direct"  # direct, linkedin, referral, etc.
    application_notes: Optional[str] = None


class CandidateUpdate(BaseModel):
    """Schema for updating candidate information."""
    full_name: Optional[str] = Field(None, min_length=2, max_length=100)
    phone: Optional[str] = None
    position_applied: Optional[str] = None
    resume_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    github_url: Optional[str] = None
    portfolio_url: Optional[str] = None
    current_company: Optional[str] = None
    years_of_experience: Optional[int] = Field(None, ge=0, le=50)
    location: Optional[str] = None
    skills: Optional[list[str]] = None
    education: Optional[str] = None
    status: Optional[CandidateStatus] = None
    tags: Optional[list[str]] = None


class CandidateInDB(CandidateBase):
    """Schema for candidate in database."""
    id: str
    user_id: Optional[str] = None
    company_id: Optional[str] = None
    status: CandidateStatus
    source: str
    tags: Optional[list[str]] = []
    application_notes: Optional[str] = None
    internal_notes: Optional[str] = None
    applied_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class CandidateResponse(CandidateBase):
    """Schema for candidate in API responses."""
    id: str
    user_id: Optional[str] = None
    company_id: Optional[str] = None
    status: CandidateStatus
    source: str
    tags: Optional[list[str]] = []
    applied_at: datetime
    
    # Aggregated data
    total_interviews: Optional[int] = 0
    completed_interviews: Optional[int] = 0
    average_rating: Optional[float] = None
    last_interview_date: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class CandidateListResponse(BaseModel):
    """Schema for paginated candidate list."""
    items: list[CandidateResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class CandidateDetailResponse(CandidateResponse):
    """Detailed candidate response with related data."""
    interviews: Optional[list[Dict[str, Any]]] = []
    evaluations: Optional[list[Dict[str, Any]]] = []
    timeline: Optional[list[Dict[str, Any]]] = []


# Bulk import schemas
class CandidateBulkImport(BaseModel):
    """Schema for bulk candidate import."""
    email: EmailStr
    full_name: str
    position_applied: str
    phone: Optional[str] = None
    resume_url: Optional[str] = None
    skills: Optional[str] = None  # comma-separated
    years_of_experience: Optional[int] = None
    source: Optional[str] = "bulk_import"


class CandidateBulkImportResponse(BaseModel):
    """Response for bulk candidate import."""
    total_candidates: int
    successfully_imported: int
    failed: int
    candidates: list[CandidateResponse]
    errors: list[Dict[str, Any]]


# Candidate notes
class CandidateNote(BaseModel):
    """Schema for candidate notes."""
    candidate_id: str
    author_id: str
    content: str = Field(..., min_length=1, max_length=2000)
    is_internal: bool = True
    created_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class CandidateNoteCreate(BaseModel):
    """Schema for creating a candidate note."""
    content: str = Field(..., min_length=1, max_length=2000)
    is_internal: bool = True
