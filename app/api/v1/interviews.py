"""
Interview API endpoints.
"""
import re
from typing import Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Query
from uuid import uuid4
from pydantic import BaseModel

from app.core.security import get_current_user_token, require_admin, require_interviewer, create_access_token
from app.core.supabase import get_supabase
from app.schemas.interview import (
    InterviewCreate,
    InterviewUpdate,
    InterviewResponse,
    InterviewListResponse,
    BulkInterviewCreate,
    BulkInterviewResponse,
    InterviewRescheduleRequest
)
from app.services.interview_service import InterviewService
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/interviews", tags=["Interviews"])

_UUID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)


class GuestJoinRequest(BaseModel):
    name: str


@router.post("/{interview_id}/guest-join", tags=["Interviews"])
async def guest_join_interview(
    interview_id: str,
    body: GuestJoinRequest,
    supabase=Depends(get_supabase)
):
    """
    Issue a temporary guest token for a candidate joining via an email link.
    No authentication is required — anyone with the room link can call this.
    """
    if _UUID_RE.match(interview_id):
        result = supabase.table("interviews").select("id, room_id, status").eq("id", interview_id).execute()
    else:
        result = supabase.table("interviews").select("id, room_id, status").eq("room_id", interview_id).execute()

    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview not found")

    interview = result.data[0]

    if interview["status"] not in ("scheduled", "in_progress"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Interview is not currently available"
        )

    guest_id = str(uuid4())
    token = create_access_token(
        data={
            "sub": guest_id,
            "name": body.name,
            "email": None,
            "role": "candidate",
            "interview_id": interview["id"],
            "room_id": interview["room_id"],
            "is_guest": True,
        },
        expires_delta=timedelta(hours=4),
    )

    return {
        "access_token": token,
        "user": {
            "id": guest_id,
            "full_name": body.name,
            "role": "candidate",
            "is_guest": True,
        },
    }


@router.post("", response_model=InterviewResponse, status_code=status.HTTP_201_CREATED)
async def create_interview(
    interview_data: InterviewCreate,
    current_user: dict = Depends(require_admin),
    supabase=Depends(get_supabase)
):
    """
    Create a new interview.
    
    - Admin only
    - Creates interview session
    - Generates unique room ID
    - Sends notifications to interviewer and candidate
    """
    service = InterviewService(supabase)
    
    # Generate unique identifiers
    interview_id = str(uuid4())
    room_id = f"room_{interview_id[:8]}"
    meeting_url = f"/interview/{room_id}"
    
    # Prepare interview data (serialize datetime to string)
    interview_dict = interview_data.model_dump(mode='json')
    interview_dict.update({
        "id": interview_id,
        "status": "scheduled",
        "room_id": room_id,
        "meeting_url": meeting_url,
        "created_by": current_user["sub"]
    })
    
    # Create interview
    result = supabase.table("interviews").insert(interview_dict).execute()
    
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to create interview"
        )
    
    interview = result.data[0]
    
    # Send notifications
    notification_service = NotificationService(supabase)
    await notification_service.send_interview_scheduled_notification(interview)
    
    # Get candidate and interviewer details
    interview_response = await service.get_interview_with_details(interview_id)
    
    return interview_response


@router.get("", response_model=InterviewListResponse)
async def list_interviews(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    interview_type: Optional[str] = None,
    interviewer_id: Optional[str] = None,
    candidate_id: Optional[str] = None,
    position: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    current_user: dict = Depends(get_current_user_token),
    supabase=Depends(get_supabase)
):
    """
    List interviews with filtering and pagination.
    
    - Filters based on user role
    - Admin: sees all company interviews
    - Interviewer: sees their interviews
    - Candidate: sees their interviews
    """
    service = InterviewService(supabase)
    user_id = current_user["sub"]
    user_role = current_user["role"]
    company_id = current_user.get("company_id")
    
    # Build query
    query = supabase.table("interviews").select("*", count="exact")
    
    # Role-based filtering
    if user_role == "candidate":
        query = query.eq("candidate_id", user_id)
    elif user_role == "interviewer":
        query = query.eq("interviewer_id", user_id)
    elif user_role == "admin" and company_id:
        query = query.eq("company_id", company_id)
    
    # Apply filters
    if status:
        query = query.eq("status", status)
    if interview_type:
        query = query.eq("interview_type", interview_type)
    if interviewer_id:
        query = query.eq("interviewer_id", interviewer_id)
    if candidate_id:
        query = query.eq("candidate_id", candidate_id)
    if position:
        query = query.ilike("position", f"%{position}%")
    if date_from:
        query = query.gte("scheduled_at", date_from.isoformat())
    if date_to:
        query = query.lte("scheduled_at", date_to.isoformat())
    
    # Pagination
    offset = (page - 1) * page_size
    query = query.order("scheduled_at", desc=True).range(offset, offset + page_size - 1)
    
    result = query.execute()
    
    total = result.count if result.count else 0
    total_pages = (total + page_size - 1) // page_size
    
    # Get detailed information for each interview
    interviews = []
    for interview in result.data:
        detailed = await service.get_interview_with_details(interview["id"])
        interviews.append(detailed)
    
    return InterviewListResponse(
        items=interviews,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@router.get("/{interview_id}", response_model=InterviewResponse)
async def get_interview(
    interview_id: str,
    current_user: dict = Depends(get_current_user_token),
    supabase=Depends(get_supabase)
):
    """
    Get interview details by ID.
    
    - Returns detailed interview information
    - Includes candidate and interviewer data
    - Includes evaluation if available
    """
    service = InterviewService(supabase)
    
    # Check access permission - support lookup by UUID id OR by room_id
    if _UUID_RE.match(interview_id):
        interview = supabase.table("interviews").select("*").eq("id", interview_id).execute()
    else:
        # Treat as room_id
        interview = supabase.table("interviews").select("*").eq("room_id", interview_id).execute()
        if interview.data:
            # Resolve actual UUID for downstream usage
            interview_id = interview.data[0]["id"]
    
    if not interview.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview not found"
        )
    
    interview_data = interview.data[0]
    user_id = current_user["sub"]
    user_role = current_user["role"]

    # Guest candidates: validate their token was issued for this specific interview
    if current_user.get("is_guest"):
        guest_interview_id = current_user.get("interview_id")
        if guest_interview_id != interview_data["id"]:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        # Guest is authorised — skip standard role checks below
        interview_response = await service.get_interview_with_details(interview_id)
        return interview_response
    
    # Check if user has access to this interview
    if user_role == "candidate" and interview_data["candidate_id"] != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    if user_role == "interviewer" and interview_data["interviewer_id"] != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    # Get detailed information
    interview_response = await service.get_interview_with_details(interview_id)
    
    return interview_response


@router.patch("/{interview_id}", response_model=InterviewResponse)
async def update_interview(
    interview_id: str,
    update_data: InterviewUpdate,
    current_user: dict = Depends(require_admin),
    supabase=Depends(get_supabase)
):
    """
    Update interview details.
    
    - Admin only
    - Can update scheduling, settings, status
    - Sends notifications on reschedule
    """
    service = InterviewService(supabase)
    
    # Check if interview exists
    interview = supabase.table("interviews").select("*").eq("id", interview_id).execute()
    
    if not interview.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview not found"
        )
    
    # Update interview (serialize datetime to string)
    update_dict = update_data.model_dump(exclude_unset=True, mode='json')
    update_dict["updated_at"] = datetime.utcnow().isoformat()
    
    result = supabase.table("interviews").update(update_dict).eq("id", interview_id).execute()
    
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to update interview"
        )
    
    # If scheduled_at changed, send reschedule notification
    if "scheduled_at" in update_dict:
        notification_service = NotificationService(supabase)
        await notification_service.send_interview_rescheduled_notification(interview_id)
    
    # Get updated interview with details
    interview_response = await service.get_interview_with_details(interview_id)
    
    return interview_response


@router.delete("/{interview_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_interview(
    interview_id: str,
    current_user: dict = Depends(require_admin),
    supabase=Depends(get_supabase)
):
    """
    Delete (cancel) an interview.
    
    - Admin only
    - Marks interview as cancelled
    - Sends cancellation notifications
    """
    # Check if interview exists
    interview = supabase.table("interviews").select("*").eq("id", interview_id).execute()
    
    if not interview.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview not found"
        )
    
    # Update status to cancelled instead of deleting
    supabase.table("interviews").update({
        "status": "cancelled",
        "updated_at": datetime.utcnow().isoformat()
    }).eq("id", interview_id).execute()
    
    # Send cancellation notification
    notification_service = NotificationService(supabase)
    await notification_service.send_interview_cancelled_notification(interview_id)
    
    return None


@router.post("/bulk", response_model=BulkInterviewResponse)
async def bulk_create_interviews(
    bulk_data: BulkInterviewCreate,
    current_user: dict = Depends(require_admin),
    supabase=Depends(get_supabase)
):
    """
    Create multiple interviews at once.
    
    - Admin only
    - Processes list of candidates
    - Optionally auto-assigns interviewers
    - Returns success/failure summary
    """
    service = InterviewService(supabase)
    
    result = await service.bulk_create_interviews(bulk_data, current_user["sub"])
    
    return result


@router.post("/{interview_id}/start")
async def start_interview(
    interview_id: str,
    current_user: dict = Depends(require_interviewer),
    supabase=Depends(get_supabase)
):
    """
    Start an interview session.
    
    - Interviewer or Admin only
    - Updates status to in_progress
    - Records actual start time
    """
    # Check if interview exists and user has access
    interview = supabase.table("interviews").select("*").eq("id", interview_id).execute()
    
    if not interview.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview not found"
        )
    
    interview_data = interview.data[0]
    
    if interview_data["interviewer_id"] != current_user["sub"] and current_user["role"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    # Update interview status
    supabase.table("interviews").update({
        "status": "in_progress",
        "actual_start_time": datetime.utcnow().isoformat()
    }).eq("id", interview_id).execute()
    
    return {"message": "Interview started", "interview_id": interview_id}


@router.post("/{interview_id}/end")
async def end_interview(
    interview_id: str,
    current_user: dict = Depends(require_interviewer),
    supabase=Depends(get_supabase)
):
    """
    End an interview session.
    
    - Interviewer or Admin only
    - Updates status to completed
    - Records actual end time
    """
    # Check if interview exists and user has access
    interview = supabase.table("interviews").select("*").eq("id", interview_id).execute()
    
    if not interview.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview not found"
        )
    
    interview_data = interview.data[0]
    
    if interview_data["interviewer_id"] != current_user["sub"] and current_user["role"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    # Update interview status
    supabase.table("interviews").update({
        "status": "completed",
        "actual_end_time": datetime.utcnow().isoformat()
    }).eq("id", interview_id).execute()
    
    return {"message": "Interview ended", "interview_id": interview_id}


@router.post("/{interview_id}/reschedule")
async def request_reschedule(
    interview_id: str,
    reschedule_data: InterviewRescheduleRequest,
    current_user: dict = Depends(get_current_user_token),
    supabase=Depends(get_supabase)
):
    """
    Request interview reschedule.
    
    - Candidate or interviewer can request
    - Admin approves/rejects
    - Creates reschedule request record
    """
    service = InterviewService(supabase)
    
    result = await service.create_reschedule_request(
        interview_id,
        current_user["sub"],
        reschedule_data
    )
    
    return result
