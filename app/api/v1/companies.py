"""
Companies API endpoints.
"""
from typing import List, Dict
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from datetime import datetime

from app.core.supabase import get_supabase, get_supabase_service
from app.core.security import get_current_user_token, verify_user_role

router = APIRouter(prefix="/companies", tags=["Companies"])


class CompanyBase(BaseModel):
    """Base company schema."""
    name: str = Field(..., min_length=2, max_length=200)
    industry: str | None = None
    company_size: str | None = None
    website: str | None = None
    description: str | None = None
    logo_url: str | None = None


class CompanyCreate(CompanyBase):
    """Schema for creating a company."""
    pass


class CompanyUpdate(BaseModel):
    """Schema for updating company information."""
    name: str | None = Field(None, min_length=2, max_length=200)
    industry: str | None = None
    company_size: str | None = None
    website: str | None = None
    description: str | None = None
    logo_url: str | None = None


class CompanyResponse(CompanyBase):
    """Schema for company in API responses."""
    id: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


@router.get("/me", response_model=CompanyResponse)
async def get_my_company(
    current_user: Dict = Depends(get_current_user_token),
):
    """Get the current user's company information."""
    supabase = get_supabase_service()
    
    company_id = current_user.get("company_id")
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No company associated with this user"
        )
    
    result = supabase.table("companies").select("*").eq("id", company_id).single().execute()
    
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found"
        )
    
    return result.data


@router.get("/{company_id}", response_model=CompanyResponse)
async def get_company(
    company_id: str,
    current_user: Dict = Depends(verify_user_role(["admin"])),
):
    """Get company by ID (admin only)."""
    supabase = get_supabase_service()
    
    result = supabase.table("companies").select("*").eq("id", company_id).single().execute()
    
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found"
        )
    
    return result.data


@router.patch("/me", response_model=CompanyResponse)
async def update_my_company(
    company_update: CompanyUpdate,
    current_user: Dict = Depends(verify_user_role(["admin"])),
):
    """Update the current user's company information (admin only)."""
    supabase = get_supabase_service()
    
    company_id = current_user.get("company_id")
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No company associated with this user"
        )
    
    # Update only provided fields
    update_data = company_update.model_dump(exclude_unset=True)
    
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update"
        )
    
    result = supabase.table("companies").update(update_data).eq("id", company_id).execute()
    
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found"
        )
    
    return result.data[0]


@router.get("", response_model=List[CompanyResponse])
async def list_companies(
    current_user: Dict = Depends(verify_user_role(["admin"])),
):
    """List all companies (admin only, typically for super admin)."""
    supabase = get_supabase_service()
    
    result = supabase.table("companies").select("*").order("name").execute()
    
    return result.data
