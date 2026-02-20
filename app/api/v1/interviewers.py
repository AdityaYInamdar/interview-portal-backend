"""
Interviewers API endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional, Dict
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime

from app.core.security import get_current_user_token, verify_user_role, require_admin
from app.core.supabase import get_supabase_service
from app.core.security import get_password_hash

router = APIRouter(prefix="/interviewers", tags=["interviewers"])


class InterviewerCreate(BaseModel):
    """Schema for creating an interviewer."""
    email: EmailStr
    full_name: str = Field(..., min_length=2, max_length=100)
    phone: Optional[str] = None
    password: str = Field(..., min_length=8, max_length=100)
    title: Optional[str] = None
    bio: Optional[str] = None
    expertise_areas: List[str] = []
    programming_languages: List[str] = []
    years_of_experience: Optional[int] = Field(None, ge=0, le=50)
    linkedin_url: Optional[str] = None


class InterviewerUpdate(BaseModel):
    """Schema for updating interviewer information."""
    full_name: Optional[str] = Field(None, min_length=2, max_length=100)
    phone: Optional[str] = None
    title: Optional[str] = None
    bio: Optional[str] = None
    expertise_areas: Optional[List[str]] = None
    programming_languages: Optional[List[str]] = None
    years_of_experience: Optional[int] = Field(None, ge=0, le=50)
    linkedin_url: Optional[str] = None
    status: Optional[str] = None


class InterviewerResponse(BaseModel):
    """Schema for interviewer in API responses."""
    id: str
    email: str
    full_name: str
    phone: Optional[str] = None
    role: str
    company_id: Optional[str] = None
    status: str
    avatar_url: Optional[str] = None
    created_at: datetime
    
    # Profile fields
    title: Optional[str] = None
    bio: Optional[str] = None
    expertise_areas: List[str] = []
    programming_languages: List[str] = []
    years_of_experience: Optional[int] = None
    linkedin_url: Optional[str] = None
    
    # Stats
    total_interviews: Optional[int] = 0
    completed_interviews: Optional[int] = 0
    average_rating: Optional[float] = None
    
    class Config:
        from_attributes = True


@router.post("/", response_model=InterviewerResponse, status_code=status.HTTP_201_CREATED)
async def create_interviewer(
    interviewer_data: InterviewerCreate,
    current_user: Dict = Depends(require_admin),
):
    """Create a new interviewer (admin only)"""
    supabase = get_supabase_service()
    
    # Check if user already exists
    existing_user = supabase.table("users").select("*").eq("email", interviewer_data.email).execute()
    if existing_user.data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Get admin's company_id
    company_id = current_user.get("company_id")
    
    try:
        # Create user in Supabase Auth
        auth_response = supabase.auth.sign_up({
            "email": interviewer_data.email,
            "password": interviewer_data.password,
            "options": {
                "email_redirect_to": None,
                "data": {
                    "full_name": interviewer_data.full_name,
                    "role": "interviewer"
                }
            }
        })
        
        if not auth_response.user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to create user account"
            )
        
        # Auto-confirm email
        try:
            supabase.auth.admin.update_user_by_id(
                auth_response.user.id,
                {"email_confirm": True}
            )
        except:
            pass
        
        # Create user profile
        user_profile = {
            "id": auth_response.user.id,
            "email": interviewer_data.email,
            "full_name": interviewer_data.full_name,
            "role": "interviewer",
            "phone": interviewer_data.phone,
            "company_id": company_id,
            "status": "active",
            "email_verified": True
        }
        
        user_result = supabase.table("users").insert(user_profile).execute()
        
        # Create interviewer profile
        profile_data = {
            "user_id": auth_response.user.id,
            "title": interviewer_data.title,
            "bio": interviewer_data.bio,
            "expertise_areas": interviewer_data.expertise_areas,
            "programming_languages": interviewer_data.programming_languages,
            "years_of_experience": interviewer_data.years_of_experience,
            "linkedin_url": interviewer_data.linkedin_url,
        }
        
        profile_result = supabase.table("interviewer_profiles").insert(profile_data).execute()
        
        # Combine user and profile data
        response_data = {**user_result.data[0]}
        if profile_result.data:
            response_data.update({
                "title": profile_result.data[0].get("title"),
                "bio": profile_result.data[0].get("bio"),
                "expertise_areas": profile_result.data[0].get("expertise_areas", []),
                "programming_languages": profile_result.data[0].get("programming_languages", []),
                "years_of_experience": profile_result.data[0].get("years_of_experience"),
                "linkedin_url": profile_result.data[0].get("linkedin_url"),
            })
        else:
            response_data.update({
                "title": None,
                "bio": None,
                "expertise_areas": [],
                "programming_languages": [],
                "years_of_experience": None,
                "linkedin_url": None,
            })
        
        response_data["total_interviews"] = 0
        response_data["completed_interviews"] = 0
        response_data["average_rating"] = None
        
        return InterviewerResponse(**response_data)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create interviewer: {str(e)}"
        )


@router.get("/", response_model=List[InterviewerResponse])
async def list_interviewers(
    status_filter: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    current_user: Dict = Depends(verify_user_role(["admin", "interviewer"])),
):
    """List all interviewers"""
    supabase = get_supabase_service()
    
    # Query users with interviewer role
    query = supabase.table("users").select("*").eq("role", "interviewer")
    
    # Filter by company
    company_id = current_user.get("company_id")
    if company_id:
        query = query.eq("company_id", company_id)
    
    # Apply filters
    if status_filter:
        query = query.eq("status", status_filter)
    
    # Pagination
    query = query.range(skip, skip + limit - 1).order("created_at", desc=True)
    
    users_result = query.execute()
    
    # Get profiles for all interviewers
    interviewers = []
    for user in users_result.data:
        # Get profile
        profile_result = supabase.table("interviewer_profiles").select("*").eq("user_id", user["id"]).execute()
        
        # Get interview stats
        interviews_result = supabase.table("interviews").select("id, status").eq("interviewer_id", user["id"]).execute()
        total_interviews = len(interviews_result.data) if interviews_result.data else 0
        completed_interviews = len([i for i in (interviews_result.data or []) if i.get("status") == "completed"])
        
        # Combine data
        interviewer_data = {**user}
        if profile_result.data:
            interviewer_data.update({
                "title": profile_result.data[0].get("title"),
                "bio": profile_result.data[0].get("bio"),
                "expertise_areas": profile_result.data[0].get("expertise_areas", []),
                "programming_languages": profile_result.data[0].get("programming_languages", []),
                "years_of_experience": profile_result.data[0].get("years_of_experience"),
                "linkedin_url": profile_result.data[0].get("linkedin_url"),
            })
        else:
            interviewer_data.update({
                "title": None,
                "bio": None,
                "expertise_areas": [],
                "programming_languages": [],
                "years_of_experience": None,
                "linkedin_url": None,
            })
        
        interviewer_data["total_interviews"] = total_interviews
        interviewer_data["completed_interviews"] = completed_interviews
        interviewer_data["average_rating"] = None
        
        interviewers.append(InterviewerResponse(**interviewer_data))
    
    return interviewers


@router.get("/{interviewer_id}", response_model=InterviewerResponse)
async def get_interviewer(
    interviewer_id: UUID,
    current_user: Dict = Depends(verify_user_role(["admin", "interviewer"])),
):
    """Get interviewer details"""
    supabase = get_supabase_service()
    
    # Get user
    user_result = supabase.table("users").select("*").eq("id", str(interviewer_id)).eq("role", "interviewer").execute()
    
    if not user_result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interviewer not found"
        )
    
    user = user_result.data[0]
    
    # Check company access
    company_id = current_user.get("company_id")
    if company_id and user.get("company_id") != company_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interviewer not found"
        )
    
    # Get profile
    profile_result = supabase.table("interviewer_profiles").select("*").eq("user_id", str(interviewer_id)).execute()
    
    # Get interview stats
    interviews_result = supabase.table("interviews").select("id, status").eq("interviewer_id", str(interviewer_id)).execute()
    total_interviews = len(interviews_result.data) if interviews_result.data else 0
    completed_interviews = len([i for i in (interviews_result.data or []) if i.get("status") == "completed"])
    
    # Combine data
    interviewer_data = {**user}
    if profile_result.data:
        interviewer_data.update({
            "title": profile_result.data[0].get("title"),
            "bio": profile_result.data[0].get("bio"),
            "expertise_areas": profile_result.data[0].get("expertise_areas", []),
            "programming_languages": profile_result.data[0].get("programming_languages", []),
            "years_of_experience": profile_result.data[0].get("years_of_experience"),
            "linkedin_url": profile_result.data[0].get("linkedin_url"),
        })
    else:
        interviewer_data.update({
            "title": None,
            "bio": None,
            "expertise_areas": [],
            "programming_languages": [],
            "years_of_experience": None,
            "linkedin_url": None,
        })
    
    interviewer_data["total_interviews"] = total_interviews
    interviewer_data["completed_interviews"] = completed_interviews
    interviewer_data["average_rating"] = None
    
    return InterviewerResponse(**interviewer_data)


@router.patch("/{interviewer_id}", response_model=InterviewerResponse)
async def update_interviewer(
    interviewer_id: UUID,
    interviewer_update: InterviewerUpdate,
    current_user: Dict = Depends(require_admin),
):
    """Update interviewer information (admin only)"""
    supabase = get_supabase_service()
    
    # Check if interviewer exists
    user_result = supabase.table("users").select("*").eq("id", str(interviewer_id)).eq("role", "interviewer").execute()
    
    if not user_result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interviewer not found"
        )
    
    # Update user fields
    user_update = {}
    if interviewer_update.full_name is not None:
        user_update["full_name"] = interviewer_update.full_name
    if interviewer_update.phone is not None:
        user_update["phone"] = interviewer_update.phone
    if interviewer_update.status is not None:
        user_update["status"] = interviewer_update.status
    
    if user_update:
        supabase.table("users").update(user_update).eq("id", str(interviewer_id)).execute()
    
    # Update profile fields
    profile_update = {}
    if interviewer_update.title is not None:
        profile_update["title"] = interviewer_update.title
    if interviewer_update.bio is not None:
        profile_update["bio"] = interviewer_update.bio
    if interviewer_update.expertise_areas is not None:
        profile_update["expertise_areas"] = interviewer_update.expertise_areas
    if interviewer_update.programming_languages is not None:
        profile_update["programming_languages"] = interviewer_update.programming_languages
    if interviewer_update.years_of_experience is not None:
        profile_update["years_of_experience"] = interviewer_update.years_of_experience
    if interviewer_update.linkedin_url is not None:
        profile_update["linkedin_url"] = interviewer_update.linkedin_url
    
    if profile_update:
        # Check if profile exists
        profile_check = supabase.table("interviewer_profiles").select("*").eq("user_id", str(interviewer_id)).execute()
        
        if profile_check.data:
            supabase.table("interviewer_profiles").update(profile_update).eq("user_id", str(interviewer_id)).execute()
        else:
            profile_update["user_id"] = str(interviewer_id)
            supabase.table("interviewer_profiles").insert(profile_update).execute()
    
    # Return updated interviewer
    return await get_interviewer(interviewer_id, current_user)


@router.delete("/{interviewer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_interviewer(
    interviewer_id: UUID,
    current_user: Dict = Depends(require_admin),
):
    """Delete an interviewer (admin only)"""
    supabase = get_supabase_service()
    
    # Check if interviewer exists
    user_result = supabase.table("users").select("*").eq("id", str(interviewer_id)).eq("role", "interviewer").execute()
    
    if not user_result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interviewer not found"
        )
    
    try:
        # Delete from auth (cascades to users and profiles)
        supabase.auth.admin.delete_user(str(interviewer_id))
        return None
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete interviewer: {str(e)}"
        )
