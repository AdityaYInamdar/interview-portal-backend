"""
Users API endpoints.
"""
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel

from app.core.security import get_current_user_token
from app.core.supabase import get_supabase


router = APIRouter(prefix="/users", tags=["Users"])


class UserResponse(BaseModel):
    """User response model."""
    id: str
    email: str
    full_name: str
    role: str
    phone: Optional[str] = None
    company_id: Optional[str] = None
    is_active: bool = True
    created_at: str


@router.get("", response_model=List[UserResponse])
async def list_users(
    role: Optional[str] = Query(None, description="Filter by role (admin, interviewer, candidate)"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    current_user: dict = Depends(get_current_user_token),
    supabase=Depends(get_supabase)
):
    """
    List users with optional filtering.
    
    - Filters based on user role permissions
    - Admin: sees all company users
    - Regular users: limited access
    """
    user_role = current_user["role"]
    company_id = current_user.get("company_id")
    
    # Build query
    query = supabase.table("users").select("*")
    
    # Admin can only see users from their company
    if user_role == "admin" and company_id:
        query = query.eq("company_id", company_id)
    elif user_role != "admin":
        # Non-admin users have limited access
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions"
        )
    
    # Apply filters
    if role:
        query = query.eq("role", role)
    if is_active is not None:
        query = query.eq("is_active", is_active)
    
    # Order by creation date
    query = query.order("created_at", desc=True)
    
    result = query.execute()
    
    if not result.data:
        return []
    
    return result.data


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    current_user: dict = Depends(get_current_user_token),
    supabase=Depends(get_supabase)
):
    """
    Get a specific user by ID.
    
    - Admin can access users in their company
    - Users can access their own profile
    """
    requesting_user_id = current_user["sub"]
    user_role = current_user["role"]
    company_id = current_user.get("company_id")
    
    # Fetch user
    result = supabase.table("users").select("*").eq("id", user_id).execute()
    
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    user = result.data[0]
    
    # Permission check
    if user_role == "admin":
        # Admin can only see users from their company
        if user.get("company_id") != company_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions"
            )
    elif user_id != requesting_user_id:
        # Regular users can only see their own profile
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions"
        )
    
    return user
