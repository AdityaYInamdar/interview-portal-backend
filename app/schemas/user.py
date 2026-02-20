"""
Pydantic schemas for User-related operations.
"""
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field
from enum import Enum


class UserRole(str, Enum):
    """User roles in the system."""
    ADMIN = "admin"
    INTERVIEWER = "interviewer"
    CANDIDATE = "candidate"


class UserStatus(str, Enum):
    """User account status."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"


# Base schemas
class UserBase(BaseModel):
    """Base user schema with common fields."""
    email: EmailStr
    full_name: str = Field(..., min_length=2, max_length=100)
    role: UserRole = UserRole.CANDIDATE
    phone: Optional[str] = None
    timezone: str = "UTC"
    avatar_url: Optional[str] = None


class UserCreate(UserBase):
    """Schema for creating a new user."""
    password: str = Field(..., min_length=8, max_length=100)
    company_name: Optional[str] = Field(None, min_length=2, max_length=200)


class UserUpdate(BaseModel):
    """Schema for updating user information."""
    full_name: Optional[str] = Field(None, min_length=2, max_length=100)
    phone: Optional[str] = None
    timezone: Optional[str] = None
    avatar_url: Optional[str] = None
    status: Optional[UserStatus] = None


class UserInDB(UserBase):
    """Schema for user as stored in database."""
    id: str
    company_id: Optional[str] = None
    status: UserStatus
    email_verified: bool
    created_at: datetime
    updated_at: datetime
    last_login: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class UserResponse(UserBase):
    """Schema for user in API responses."""
    id: str
    company_id: Optional[str] = None
    status: UserStatus
    email_verified: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


# Authentication schemas
class Token(BaseModel):
    """JWT token response."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse


class TokenRefresh(BaseModel):
    """Schema for refreshing tokens."""
    refresh_token: str


class LoginRequest(BaseModel):
    """Login request schema."""
    email: EmailStr
    password: str


class PasswordChange(BaseModel):
    """Schema for changing password."""
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=100)


class PasswordReset(BaseModel):
    """Schema for password reset."""
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    """Schema for confirming password reset."""
    token: str
    new_password: str = Field(..., min_length=8, max_length=100)


# Interviewer-specific schemas
class InterviewerProfile(BaseModel):
    """Extended profile for interviewers."""
    user_id: str
    title: Optional[str] = None
    bio: Optional[str] = None
    expertise_areas: list[str] = []
    programming_languages: list[str] = []
    years_of_experience: Optional[int] = None
    linkedin_url: Optional[str] = None
    
    class Config:
        from_attributes = True


class InterviewerAvailability(BaseModel):
    """Interviewer availability settings."""
    user_id: str
    available_days: list[str] = []  # ["monday", "tuesday", ...]
    available_hours_start: str = "09:00"
    available_hours_end: str = "17:00"
    buffer_time_minutes: int = 15
    max_interviews_per_day: int = 5
    unavailable_dates: list[str] = []  # ISO date strings
    
    class Config:
        from_attributes = True
