"""
Pydantic schemas for Evaluation-related operations.
"""
from typing import Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum


class OverallRecommendation(str, Enum):
    """Overall hiring recommendation."""
    STRONG_HIRE = "strong_hire"
    HIRE = "hire"
    MAYBE = "maybe"
    NO_HIRE = "no_hire"
    STRONG_NO_HIRE = "strong_no_hire"


class EvaluationBase(BaseModel):
    """Base evaluation schema."""
    interview_id: str
    technical_skills: Optional[int] = Field(None, ge=1, le=5)
    problem_solving: Optional[int] = Field(None, ge=1, le=5)
    communication: Optional[int] = Field(None, ge=1, le=5)
    cultural_fit: Optional[int] = Field(None, ge=1, le=5)
    overall_rating: Optional[int] = Field(None, ge=1, le=5)
    recommendation: OverallRecommendation
    strengths: Optional[str] = None
    weaknesses: Optional[str] = None
    detailed_feedback: Optional[str] = None
    notes: Optional[str] = None
    custom_ratings: Optional[Dict[str, int]] = None


class EvaluationCreate(EvaluationBase):
    """Schema for creating an evaluation."""
    evaluator_id: str


class EvaluationUpdate(BaseModel):
    """Schema for updating an evaluation."""
    technical_skills: Optional[int] = Field(None, ge=1, le=5)
    problem_solving: Optional[int] = Field(None, ge=1, le=5)
    communication: Optional[int] = Field(None, ge=1, le=5)
    cultural_fit: Optional[int] = Field(None, ge=1, le=5)
    overall_rating: Optional[int] = Field(None, ge=1, le=5)
    recommendation: Optional[OverallRecommendation] = None
    strengths: Optional[str] = None
    weaknesses: Optional[str] = None
    detailed_feedback: Optional[str] = None
    notes: Optional[str] = None


class EvaluationInDB(EvaluationBase):
    """Schema for evaluation in database."""
    id: str
    evaluator_id: str
    submitted_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class EvaluationResponse(EvaluationBase):
    """Schema for evaluation in API responses."""
    id: str
    evaluator_id: str
    submitted_at: datetime
    evaluator: Optional[Dict[str, Any]] = None
    
    class Config:
        from_attributes = True


# Evaluation templates
class EvaluationTemplate(BaseModel):
    """Schema for evaluation templates."""
    id: Optional[str] = None
    name: str
    description: Optional[str] = None
    company_id: str
    criteria: Dict[str, Any]
    created_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class EvaluationTemplateCreate(BaseModel):
    """Schema for creating evaluation template."""
    name: str = Field(..., min_length=3, max_length=100)
    description: Optional[str] = None
    criteria: Dict[str, Any]


class EvaluationTemplateUpdate(BaseModel):
    """Schema for updating evaluation template."""
    name: Optional[str] = Field(None, min_length=3, max_length=100)
    description: Optional[str] = None
    criteria: Optional[Dict[str, Any]] = None
