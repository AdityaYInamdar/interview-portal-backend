"""
Interview Service - Business logic for interview operations.
"""
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from uuid import uuid4

from app.schemas.interview import (
    InterviewResponse,
    BulkInterviewCreate,
    BulkInterviewResponse,
    InterviewRescheduleRequest
)


class InterviewService:
    """Service class for interview-related operations."""
    
    def __init__(self, supabase_client):
        self.db = supabase_client
    
    async def get_interview_with_details(self, interview_id: str) -> InterviewResponse:
        """
        Get interview with candidate, interviewer, and evaluation details.
        """
        # Get interview
        interview_result = self.db.table("interviews").select("*").eq("id", interview_id).execute()
        
        if not interview_result.data:
            return None
        
        interview = interview_result.data[0]
        
        # Get candidate details
        candidate_result = self.db.table("candidates").select("*").eq("id", interview["candidate_id"]).execute()
        candidate = candidate_result.data[0] if candidate_result.data else None
        
        # Get interviewer details
        interviewer_result = self.db.table("users").select("id, full_name, email, avatar_url").eq("id", interview["interviewer_id"]).execute()
        interviewer = interviewer_result.data[0] if interviewer_result.data else None
        
        # Get evaluation if exists
        evaluation_result = self.db.table("evaluations").select("*").eq("interview_id", interview_id).execute()
        evaluation = evaluation_result.data[0] if evaluation_result.data else None
        
        # Construct response
        interview["candidate"] = candidate
        interview["interviewer"] = interviewer
        interview["evaluation"] = evaluation
        
        return InterviewResponse(**interview)
    
    async def bulk_create_interviews(
        self,
        bulk_data: BulkInterviewCreate,
        created_by: str
    ) -> BulkInterviewResponse:
        """
        Create multiple interviews from bulk data.
        """
        successfully_scheduled = 0
        failed = 0
        interviews = []
        errors = []
        
        # Get available interviewers if auto-assign is enabled
        available_interviewers = []
        if bulk_data.auto_assign and bulk_data.interviewer_ids:
            available_interviewers = bulk_data.interviewer_ids
        
        interviewer_index = 0
        
        for candidate_data in bulk_data.candidates:
            try:
                # Check if candidate exists, if not create
                candidate_result = self.db.table("candidates").select("*").eq("email", candidate_data.email).execute()
                
                if candidate_result.data:
                    candidate_id = candidate_result.data[0]["id"]
                else:
                    # Create new candidate
                    new_candidate = {
                        "id": str(uuid4()),
                        "email": candidate_data.email,
                        "full_name": candidate_data.full_name,
                        "position_applied": candidate_data.position,
                        "resume_url": candidate_data.resume_url,
                        "company_id": bulk_data.company_id,
                        "status": "interview_scheduled",
                        "source": "bulk_import"
                    }
                    candidate_create_result = self.db.table("candidates").insert(new_candidate).execute()
                    candidate_id = candidate_create_result.data[0]["id"]
                
                # Assign interviewer
                if bulk_data.auto_assign and available_interviewers:
                    interviewer_id = available_interviewers[interviewer_index % len(available_interviewers)]
                    interviewer_index += 1
                elif bulk_data.interviewer_ids:
                    interviewer_id = bulk_data.interviewer_ids[0]
                else:
                    raise Exception("No interviewer assigned")
                
                # Find available time slot
                scheduled_at = await self._find_available_slot(
                    interviewer_id,
                    bulk_data.date_range_start,
                    bulk_data.date_range_end,
                    bulk_data.duration_minutes
                )
                
                if not scheduled_at:
                    raise Exception("No available time slot found")
                
                # Create interview
                interview_id = str(uuid4())
                room_id = f"room_{interview_id[:8]}"
                
                interview = {
                    "id": interview_id,
                    "title": f"{candidate_data.position} Interview",
                    "position": candidate_data.position,
                    "interview_type": bulk_data.interview_type,
                    "duration_minutes": bulk_data.duration_minutes,
                    "scheduled_at": scheduled_at.isoformat(),
                    "candidate_id": candidate_id,
                    "interviewer_id": interviewer_id,
                    "company_id": bulk_data.company_id,
                    "status": "scheduled",
                    "room_id": room_id,
                    "meeting_url": f"/interview/{room_id}",
                    "recording_enabled": bulk_data.recording_enabled,
                    "code_editor_enabled": bulk_data.code_editor_enabled,
                    "whiteboard_enabled": bulk_data.whiteboard_enabled,
                    "round_number": 1,
                    "created_by": created_by
                }
                
                result = self.db.table("interviews").insert(interview).execute()
                
                if result.data:
                    interviews.append(InterviewResponse(**result.data[0]))
                    successfully_scheduled += 1
                else:
                    failed += 1
                    errors.append({
                        "candidate": candidate_data.email,
                        "error": "Failed to insert interview"
                    })
                    
            except Exception as e:
                failed += 1
                errors.append({
                    "candidate": candidate_data.email,
                    "error": str(e)
                })
        
        return BulkInterviewResponse(
            total_candidates=len(bulk_data.candidates),
            successfully_scheduled=successfully_scheduled,
            failed=failed,
            interviews=interviews,
            errors=errors
        )
    
    async def _find_available_slot(
        self,
        interviewer_id: str,
        start_date: datetime,
        end_date: datetime,
        duration_minutes: int
    ) -> Optional[datetime]:
        """
        Find an available time slot for the interviewer.
        Simple implementation - can be enhanced with more sophisticated scheduling.
        """
        # Get interviewer's existing interviews in the date range
        existing_interviews = self.db.table("interviews").select("scheduled_at, duration_minutes").eq(
            "interviewer_id", interviewer_id
        ).gte(
            "scheduled_at", start_date.isoformat()
        ).lte(
            "scheduled_at", end_date.isoformat()
        ).execute()
        
        # Simple algorithm: try 9 AM to 5 PM slots
        current_slot = start_date.replace(hour=9, minute=0, second=0, microsecond=0)
        
        while current_slot < end_date:
            # Check if this slot conflicts with existing interviews
            is_available = True
            
            for interview in existing_interviews.data:
                interview_start = datetime.fromisoformat(interview["scheduled_at"].replace("Z", "+00:00"))
                interview_end = interview_start + timedelta(minutes=interview["duration_minutes"])
                slot_end = current_slot + timedelta(minutes=duration_minutes)
                
                # Check for overlap
                if (current_slot < interview_end and slot_end > interview_start):
                    is_available = False
                    break
            
            if is_available:
                return current_slot
            
            # Move to next 30-minute slot
            current_slot += timedelta(minutes=30)
            
            # Skip to next day at 9 AM if after 5 PM
            if current_slot.hour >= 17:
                current_slot = current_slot + timedelta(days=1)
                current_slot = current_slot.replace(hour=9, minute=0, second=0, microsecond=0)
        
        return None
    
    async def create_reschedule_request(
        self,
        interview_id: str,
        requested_by: str,
        reschedule_data: InterviewRescheduleRequest
    ) -> Dict[str, Any]:
        """
        Create a reschedule request for an interview.
        """
        request_id = str(uuid4())
        
        request = {
            "id": request_id,
            "interview_id": interview_id,
            "requested_by": requested_by,
            "reason": reschedule_data.reason,
            "proposed_times": [t.isoformat() for t in reschedule_data.proposed_times],
            "status": "pending"
        }
        
        result = self.db.table("reschedule_requests").insert(request).execute()
        
        return result.data[0] if result.data else None
    
    async def get_interviewer_availability(
        self,
        interviewer_id: str,
        date: datetime
    ) -> List[Dict[str, Any]]:
        """
        Get available time slots for an interviewer on a given date.
        """
        # Get interviewer's availability settings
        availability_result = self.db.table("interviewer_availability").select("*").eq(
            "user_id", interviewer_id
        ).execute()
        
        if not availability_result.data:
            # Default availability: 9 AM - 5 PM
            return self._generate_default_slots(date)
        
        availability = availability_result.data[0]
        
        # Get existing interviews for the date
        date_start = date.replace(hour=0, minute=0, second=0)
        date_end = date.replace(hour=23, minute=59, second=59)
        
        existing_interviews = self.db.table("interviews").select("scheduled_at, duration_minutes").eq(
            "interviewer_id", interviewer_id
        ).gte(
            "scheduled_at", date_start.isoformat()
        ).lte(
            "scheduled_at", date_end.isoformat()
        ).execute()
        
        # Generate available slots based on availability settings and existing interviews
        slots = self._generate_available_slots(availability, existing_interviews.data, date)
        
        return slots
    
    def _generate_default_slots(self, date: datetime) -> List[Dict[str, Any]]:
        """Generate default 30-minute slots from 9 AM to 5 PM."""
        slots = []
        current = date.replace(hour=9, minute=0, second=0)
        end = date.replace(hour=17, minute=0, second=0)
        
        while current < end:
            slots.append({
                "start": current.isoformat(),
                "end": (current + timedelta(minutes=30)).isoformat(),
                "available": True
            })
            current += timedelta(minutes=30)
        
        return slots
    
    def _generate_available_slots(
        self,
        availability: Dict[str, Any],
        existing_interviews: List[Dict[str, Any]],
        date: datetime
    ) -> List[Dict[str, Any]]:
        """Generate available slots based on availability settings and existing bookings."""
        # This is a simplified implementation
        # In production, you'd want more sophisticated logic
        return self._generate_default_slots(date)
