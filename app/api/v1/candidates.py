from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from typing import List, Optional, Dict
from uuid import UUID
import csv
import io

from app.core.security import get_current_user_token, verify_user_role, require_admin
from app.core.supabase import get_supabase_service
from app.schemas.candidate import (
    CandidateCreate,
    CandidateUpdate,
    CandidateResponse,
    CandidateBulkImport,
    CandidateNote,
)
from app.services.resume_parser import ResumeParser

router = APIRouter(prefix="/candidates", tags=["candidates"])


@router.post("/", response_model=CandidateResponse, status_code=status.HTTP_201_CREATED)
async def create_candidate(
    candidate_data: CandidateCreate,
    current_user: Dict = Depends(require_admin),
):
    """Create a new candidate"""
    supabase = get_supabase_service()

    # Use company_id from current_user if not provided
    company_id = candidate_data.company_id or current_user.get("company_id")

    # Create candidate
    result = supabase.table("candidates").insert(
        {
            "full_name": candidate_data.full_name,
            "email": candidate_data.email,
            "phone": candidate_data.phone,
            "resume_url": candidate_data.resume_url,
            "linkedin_url": candidate_data.linkedin_url,
            "github_url": candidate_data.github_url,
            "portfolio_url": candidate_data.portfolio_url,
            "position_applied": candidate_data.position_applied,
            "years_of_experience": candidate_data.years_of_experience,
            "current_company": candidate_data.current_company,
            "location": candidate_data.location,
            "education": candidate_data.education,
            "skills": candidate_data.skills,
            "status": "applied",  # Default status
            "company_id": company_id,
            "source": candidate_data.source,
            "application_notes": candidate_data.application_notes,
        }
    ).execute()

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create candidate",
        )

    return result.data[0]


@router.get("/", response_model=List[CandidateResponse])
async def list_candidates(
    status_filter: Optional[str] = None,
    position: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    current_user: Dict = Depends(verify_user_role(["admin", "interviewer"])),
):
    """List all candidates with optional filtering"""
    supabase = get_supabase_service()

    query = supabase.table("candidates").select("*")

    # Filter by company (if user has a company)
    company_id = current_user.get("company_id")
    if company_id:
        query = query.eq("company_id", company_id)

    # Apply filters
    if status_filter:
        query = query.eq("status", status_filter)
    if position:
        query = query.ilike("position_applied", f"%{position}%")

    # Pagination
    query = query.range(skip, skip + limit - 1).order("updated_at", desc=True)

    result = query.execute()
    return result.data


@router.post("/parse-resume")
async def parse_resume(
    file: UploadFile = File(...),
    current_user: Dict = Depends(verify_user_role(["admin", "interviewer"])),
):
    """
    Parse a resume file (PDF, DOCX, TXT) and extract candidate information.
    
    Returns structured data that can be used to auto-fill the candidate form.
    """
    # Validate file size (max 5MB)
    content = await file.read()
    await file.seek(0)  # Reset file pointer
    
    if len(content) > 5 * 1024 * 1024:  # 5MB
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File size exceeds 5MB limit"
        )
    
    # Validate file type
    allowed_types = ['application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'text/plain']
    allowed_extensions = ['.pdf', '.docx', '.txt']
    
    if not any(file.filename.lower().endswith(ext) for ext in allowed_extensions):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file type. Please upload PDF, DOCX, or TXT file."
        )
    
    try:
        # Parse the resume
        parsed_data = await ResumeParser.parse_resume(file)
        
        return {
            "success": True,
            "data": parsed_data,
            "message": "Resume parsed successfully"
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to parse resume: {str(e)}"
        )


@router.get("/{candidate_id}", response_model=CandidateResponse)
async def get_candidate(
    candidate_id: UUID,
    current_user: Dict = Depends(verify_user_role(["admin", "interviewer"])),
):
    """Get candidate details"""
    supabase = get_supabase_service()

    query = supabase.table("candidates").select("*").eq("id", str(candidate_id))
    
    # Filter by company if user has one
    company_id = current_user.get("company_id")
    if company_id:
        query = query.eq("company_id", company_id)
    
    result = query.single().execute()

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate not found",
        )

    return result.data


@router.patch("/{candidate_id}", response_model=CandidateResponse)
async def update_candidate(
    candidate_id: UUID,
    candidate_update: CandidateUpdate,
    current_user: Dict = Depends(require_admin),
):
    """Update candidate information"""
    supabase = get_supabase_service()

    # Check if candidate exists
    query = supabase.table("candidates").select("id").eq("id", str(candidate_id))
    
    company_id = current_user.get("company_id")
    if company_id:
        query = query.eq("company_id", company_id)
    
    existing = query.single().execute()

    if not existing.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate not found",
        )

    # Update only provided fields
    update_data = candidate_update.model_dump(exclude_unset=True)

    result = (
        supabase.table("candidates")
        .update(update_data)
        .eq("id", str(candidate_id))
        .execute()
    )

    return result.data[0]


@router.delete("/{candidate_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_candidate(
    candidate_id: UUID,
    current_user: Dict = Depends(require_admin),
):
    """Delete a candidate"""
    supabase = get_supabase_service()

    query = supabase.table("candidates").delete().eq("id", str(candidate_id))
    
    company_id = current_user.get("company_id")
    if company_id:
        query = query.eq("company_id", company_id)
    
    result = query.execute()

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate not found",
        )

    return None


@router.post("/bulk-import", response_model=dict)
async def bulk_import_candidates(
    file: UploadFile = File(...),
    current_user: Dict = Depends(require_admin),
):
    """Bulk import candidates from CSV file"""
    if not file.filename.endswith('.csv'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only CSV files are allowed",
        )

    try:
        contents = await file.read()
        csv_data = io.StringIO(contents.decode('utf-8'))
        reader = csv.DictReader(csv_data)

        supabase = get_supabase_service()
        imported_count = 0
        failed_count = 0
        errors = []

        for row in reader:
            try:
                candidate_data = {
                    "full_name": row.get("full_name"),
                    "email": row.get("email"),
                    "phone": row.get("phone"),
                    "position_applied": row.get("position_applied"),
                    "experience_years": int(row.get("experience_years", 0)),
                    "skills": row.get("skills", "").split(",") if row.get("skills") else [],
                    "status": row.get("status", "new"),
                    "company_id": current_user.get("company_id"),
                    "resume_url": row.get("resume_url"),
                    "linkedin_url": row.get("linkedin_url"),
                    "github_url": row.get("github_url"),
                }

                supabase.table("candidates").insert(candidate_data).execute()
                imported_count += 1
            except Exception as e:
                failed_count += 1
                errors.append(f"Row {imported_count + failed_count}: {str(e)}")

        return {
            "message": "Bulk import completed",
            "imported": imported_count,
            "failed": failed_count,
            "errors": errors[:10],  # Return only first 10 errors
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process CSV: {str(e)}",
        )


@router.post("/{candidate_id}/notes", response_model=CandidateNote)
async def add_candidate_note(
    candidate_id: UUID,
    note_text: str,
    current_user: Dict = Depends(get_current_user_token),
):
    """Add a note to a candidate"""
    supabase = get_supabase_service()

    # Verify candidate exists
    query = supabase.table("candidates").select("id").eq("id", str(candidate_id))
    
    company_id = current_user.get("company_id")
    if company_id:
        query = query.eq("company_id", company_id)
    
    candidate = query.single().execute()

    if not candidate.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate not found",
        )

    # Create note
    result = supabase.table("candidate_notes").insert(
        {
            "candidate_id": str(candidate_id),
            "user_id": current_user.get("sub"),
            "note": note_text,
        }
    ).execute()

    return result.data[0]


@router.get("/{candidate_id}/notes", response_model=List[CandidateNote])
async def get_candidate_notes(
    candidate_id: UUID,
    current_user: Dict = Depends(verify_user_role(["admin", "interviewer"])),
):
    """Get all notes for a candidate"""
    supabase = get_supabase_service()

    result = (
        supabase.table("candidate_notes")
        .select("*, users(full_name)")
        .eq("candidate_id", str(candidate_id))
        .order("created_at", desc=True)
        .execute()
    )

    return result.data


@router.get("/{candidate_id}/interviews", response_model=List[dict])
async def get_candidate_interviews(
    candidate_id: UUID,
    current_user: Dict = Depends(verify_user_role(["admin", "interviewer"])),
):
    """Get all interviews for a candidate"""
    supabase = get_supabase_service()

    result = (
        supabase.table("interviews")
        .select("*, users!interviewer_id(full_name)")
        .eq("candidate_id", str(candidate_id))
        .order("scheduled_at", desc=True)
        .execute()
    )

    return result.data
