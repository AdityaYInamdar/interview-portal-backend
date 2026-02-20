"""
Test Sessions API endpoints
Handles invitations, session start, submissions, and grading
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request, UploadFile, File, Form
from typing import List, Optional
from app.schemas.test import (
    TestInvitationCreate, TestInvitationBulkCreate, TestInvitationResponse,
    TestSessionStart, TestSessionResponse, TestSessionAdminReview, TestSessionResetRequest
)
from app.schemas.question import (
    QuestionForCandidate, SubmissionCreate,SubmissionResponse,
    ManualGrading, CodeExecutionRequest, CodeExecutionResponse
)
from app.services.session_manager import SessionManager
from app.services.grading_engine import GradingEngine
from app.services.email_service import EmailService
from app.core.supabase import get_supabase_client, SupabaseClient
from app.core.security import get_current_user, require_role
from datetime import datetime
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sessions", tags=["sessions"])

session_manager = SessionManager()
grading_engine = GradingEngine()
email_service = EmailService()


# ============================================
# Invitation Management
# ============================================

@router.post("/invitations", response_model=TestInvitationResponse)
async def create_invitation(
    invitation_data: TestInvitationCreate,
    current_user: dict = Depends(require_role(["admin"]))
):
    """Create test invitation and send email"""
    try:
        # Create invitation
        invitation = await session_manager.create_invitation(
            test_id=invitation_data.test_id,
            candidate_email=invitation_data.candidate_email,
            candidate_name=invitation_data.candidate_name,
            expires_in_hours=invitation_data.expires_in_hours,
            created_by=current_user['id'],
            company_id=current_user['company_id']
        )
        
        # Get test details for email
        supabase = get_supabase_client()
        test_response = supabase.table('tests').select('*').eq(
            'id', invitation_data.test_id
        ).single().execute()
        
        test = test_response.data if test_response.data else {}
        
        # Send invitation email
        base_url = "http://localhost:5173"  # TODO: Make configurable
        invitation_url = f"{base_url}/test/start?token={invitation['invitation_token']}"
        
        await email_service.send_test_invitation(
            candidate_email=invitation_data.candidate_email,
            candidate_name=invitation_data.candidate_name,
            test_title=test.get('title', 'Coding Assessment'),
            test_duration=test.get('duration_minutes', 60),
            invitation_url=invitation_url,
            expires_at=invitation['expires_at']
        )
        
        return {**invitation, 'invitation_url': invitation_url}
        
    except Exception as e:
        logger.error(f"Error creating invitation: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/invitations/bulk")
async def create_bulk_invitations(
    invitation_data: TestInvitationBulkCreate,
    current_user: dict = Depends(require_role(["admin"]))
):
    """Create multiple invitations"""
    try:
        result = await session_manager.create_bulk_invitations(
            test_id=invitation_data.test_id,
            candidates=invitation_data.candidates,
            expires_in_hours=invitation_data.expires_in_hours,
            created_by=current_user['id'],
            company_id=current_user['company_id']
        )
        
        # Send emails for successful invitations
        supabase = get_supabase_client()
        test_response = supabase.table('tests').select('*').eq(
            'id', invitation_data.test_id
        ).single().execute()
        
        test = test_response.data if test_response.data else {}
        base_url = "http://localhost:5173"
        
        for invitation in result['invitations']:
            invitation_url = f"{base_url}/test/start?token={invitation['invitation_token']}"
            try:
                await email_service.send_test_invitation(
                    candidate_email=invitation['candidate_email'],
                    candidate_name=invitation['candidate_name'],
                    test_title=test.get('title', 'Coding Assessment'),
                    test_duration=test.get('duration_minutes', 60),
                    invitation_url=invitation_url,
                    expires_at=invitation['expires_at']
                )
            except Exception as email_error:
                logger.error(f"Failed to send email to {invitation['candidate_email']}: {email_error}")
        
        return result
        
    except Exception as e:
        logger.error(f"Error creating bulk invitations: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/invitations/validate/{invitation_token}")
async def validate_invitation_token(invitation_token: str):
    """Validate invitation token (Public endpoint - before starting test)"""
    try:
        validation = await session_manager.validate_invitation(invitation_token)
        
        if not validation.get('valid'):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=validation.get('error', 'Invalid or expired invitation')
            )
        
        # Return invitation and test details (without starting session)
        return {
            'valid': True,
            'is_resuming': validation.get('is_resuming', False),
            'invitation': validation['invitation'],
            'test': validation['test'],
            'session': validation.get('session'),
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error validating invitation: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Session validation failed: {str(e)}"
        )


@router.get("/invitations/{test_id}", response_model=List[TestInvitationResponse])
async def list_invitations(
    test_id: str,
    current_user: dict = Depends(require_role(["admin"]))
):
    """List all invitations for a test"""
    try:
        supabase = get_supabase_client()
        
        # Verify test ownership
        test_check = supabase.table('tests').select('id').eq(
            'id', test_id
        ).eq('company_id', current_user['company_id']).single().execute()
        
        if not test_check.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Test not found"
            )
        
        # Get invitations
        response = supabase.table('test_invitations').select('*').eq(
            'test_id', test_id
        ).order('created_at', desc=True).execute()
        
        invitations = response.data or []
        base_url = "http://localhost:5173"
        
        for inv in invitations:
            inv['invitation_url'] = f"{base_url}/test/start?token={inv['invitation_token']}"
        
        return invitations
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing invitations: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# ============================================
# Session Start (Candidate)
# ============================================

@router.post("/start", response_model=TestSessionResponse)
async def start_test_session(
    session_data: TestSessionStart,
    request: Request
):
    """Start test session using invitation token (Public endpoint)"""
    try:
        # Extract client info
        client_ip = request.client.host if request.client else None
        user_agent = request.headers.get('user-agent')
        
        # Start session
        result = await session_manager.start_session(
            invitation_token=session_data.invitation_token,
            ip_address=client_ip,
            user_agent=user_agent
        )
        
        if not result.get('success'):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get('error', 'Failed to start session')
            )
        
        return result['session']
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting session: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/validate/{session_token}", response_model=TestSessionResponse)
async def validate_session(session_token: str):
    """Validate and get session details (Public endpoint)"""
    try:
        validation = await session_manager.validate_session(session_token)
        
        if not validation.get('valid'):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=validation.get('error', 'Invalid session')
            )
        
        return validation['session']
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error validating session: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# ============================================
# Get Test Questions (Candidate)
# ============================================

@router.get("/{session_token}/questions", response_model=List[QuestionForCandidate])
async def get_test_questions(session_token: str):
    """Get questions for active session (sanitized for candidate)"""
    try:
        # Validate session
        validation = await session_manager.validate_session(session_token)
        
        if not validation.get('valid'):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=validation.get('error')
            )
        
        session = validation['session']
        
        # Get test questions (use service client for public access)
        supabase_service = SupabaseClient.get_service_client()
        questions_response = supabase_service.table('test_questions').select(
            '*, questions(*)'
        ).eq('test_id', session['test_id']).order('question_order').execute()
        
        test_questions = questions_response.data or []
        
        # Sanitize questions (hide answers, solutions)
        sanitized = []
        for tq in test_questions:
            q = tq['questions']
            sanitized_q = {
                'id': q['id'],
                'title': q['title'],
                'description': q['description'],
                'question_type': q['question_type'],
                'difficulty': q['difficulty'],
                'marks': q['marks'],
                'code_template': q.get('code_template'),
                'time_limit': q.get('time_limit'),
                'memory_limit': q.get('memory_limit'),
                'sql_schema': q.get('sql_schema'),
                'sql_seed_data': q.get('sql_seed_data'),
                'is_multiple_correct': q.get('is_multiple_correct')
            }
            
            # For MCQ, hide is_correct flag
            if q.get('mcq_options'):
                sanitized_q['mcq_options'] = [
                    {'id': opt['id'], 'text': opt['text']}
                    for opt in q['mcq_options']
                ]
            
            sanitized.append(sanitized_q)
        
        return sanitized
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting questions: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# ============================================
# Submit Answer
# ============================================

@router.post("/{session_token}/submit", response_model=SubmissionResponse)
async def submit_answer(
    session_token: str,
    submission_data: SubmissionCreate
):
    """Submit answer for a question"""
    try:
        # Validate session
        validation = await session_manager.validate_session(session_token)
        
        if not validation.get('valid'):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=validation.get('error')
            )
        
        session = validation['session']
        
        # Get question details (use service client for public access)
        supabase_service = SupabaseClient.get_service_client()
        question_response = supabase_service.table('questions').select('*').eq(
            'id', submission_data.question_id
        ).single().execute()
        
        if not question_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Question not found"
            )
        
        question = question_response.data
        
        # Create or update submission (use service client)
        existing_submission = supabase_service.table('submissions').select('*').eq(
            'session_id', session['id']
        ).eq('question_id', submission_data.question_id).execute()
        
        submission_dict = {
            'session_id': session['id'],
            'question_id': submission_data.question_id,
            'question_type': question['question_type'],
            'code_answer': submission_data.code_answer,
            'mcq_selected_options': submission_data.mcq_selected_options,
            'text_answer': submission_data.text_answer,
            'max_marks': question['marks'],
            'status': 'pending',
            # Clear previous grading results when resubmitting
            'execution_error': None,
            'execution_output': None,
            'is_correct': None,
            'marks_obtained': 0,  # Must be number, not None
            'test_cases_passed': 0,  # Must be integer, not None
            'test_cases_total': 0,  # Must be integer, not None
            'grader_feedback': None
        }
        
        if existing_submission.data and len(existing_submission.data) > 0:
            # Update existing
            response = supabase_service.table('submissions').update(submission_dict).eq(
                'id', existing_submission.data[0]['id']
            ).execute()
            submission_id = existing_submission.data[0]['id']
        else:
            # Create new
            response = supabase_service.table('submissions').insert(submission_dict).execute()
            if not response.data:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create submission"
                )
            submission_id = response.data[0]['id']
        
        # Auto-grade if applicable
        answer_data = submission_data.model_dump()
        grading_result = await grading_engine.grade_submission(
            submission_id=submission_id,
            question_data=question,
            answer_data=answer_data
        )
        
        # Filter grading result to only include columns that exist in submissions table
        # (grading_type and grading_details go to grading_logs only)
        submission_update_fields = {
            'status', 'is_correct', 'marks_obtained', 'max_marks', 
            'auto_graded', 'manually_graded', 'execution_output', 
            'execution_error', 'execution_time_ms', 'test_cases_passed', 
            'test_cases_total', 'grader_feedback', 'memory_used_mb'
        }
        filtered_result = {k: v for k, v in grading_result.items() if k in submission_update_fields}
        
        # Update submission with grading result (use service client)
        logger.info(f"[SUBMIT] execution_output in grading_result: {'execution_output' in grading_result}, length: {len(grading_result.get('execution_output', '')) if grading_result.get('execution_output') else 0}")
        supabase_service.table('submissions').update(filtered_result).eq('id', submission_id).execute()
        
        # Recalculate session score
        await grading_engine.calculate_session_score(session['id'])
        
        # Get updated submission (use service client)
        final_submission = supabase_service.table('submissions').select('*').eq(
            'id', submission_id
        ).single().execute()
        
        # Return the submission data (frontend will hide grading results from display)
        return final_submission.data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting answer: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# ============================================
# Activity Logging
# ============================================

@router.post("/{session_token}/activity")
async def log_session_activity(
    session_token: str,
    activity_data: dict
):
    """Log candidate activity (tab switches, copy attempts, etc.)"""
    try:
        # Validate session
        validation = await session_manager.validate_session(session_token)
        
        if not validation.get('valid'):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=validation.get('error')
            )
        
        session = validation['session']
        
        # Log activity
        await session_manager.log_activity(
            session_id=session['id'],
            activity_type=activity_data.get('activity_type', 'unknown'),
            activity_data=activity_data.get('activity_data', {})
        )
        
        return {"success": True, "message": "Activity logged"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error logging activity: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# ============================================
# Complete Session
# ============================================

@router.post("/{session_token}/complete", response_model=TestSessionResponse)
async def complete_session(session_token: str):
    """Complete test session (final submit) — idempotent"""
    try:
        # Fetch session directly first so we can handle already-completed cases
        # gracefully (sendBeacon on tab-close can race with the normal submit button).
        supabase_service = SupabaseClient.get_service_client()
        session_lookup = supabase_service.table('test_sessions') \
            .select('*') \
            .eq('session_token', session_token) \
            .single() \
            .execute()

        if not session_lookup.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail='Invalid session token'
            )

        session_row = session_lookup.data

        # Idempotent: already completed/expired — return current state, no error
        if session_row.get('is_completed') or session_row.get('status') in ('completed', 'expired'):
            return session_row

        # Validate the session is still active (also auto-expires if time passed)
        validation = await session_manager.validate_session(session_token)

        if not validation.get('valid'):
            # Session may have just been expired by validate_session — return it
            fresh = supabase_service.table('test_sessions') \
                .select('*') \
                .eq('session_token', session_token) \
                .single() \
                .execute()
            if fresh.data and fresh.data.get('is_completed'):
                return fresh.data
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=validation.get('error')
            )

        session = validation['session']

        # Complete session
        result = await session_manager.complete_session(session['id'])

        # Final score calculation
        await grading_engine.calculate_session_score(session['id'])

        return result['session']

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error completing session: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# ============================================
# Admin Session Management
# ============================================

@router.get("/admin/test/{test_id}", response_model=List[TestSessionResponse])
async def list_test_sessions(
    test_id: str,
    current_user: dict = Depends(require_role(["admin"]))
):
    """List all sessions for a test (Admin)"""
    try:
        supabase = get_supabase_client()
        
        # Verify test ownership
        test_check = supabase.table('tests').select('id').eq(
            'id', test_id
        ).eq('company_id', current_user['company_id']).single().execute()
        
        if not test_check.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Test not found"
            )
        
        # Get sessions
        response = supabase.table('test_sessions').select('*').eq(
            'test_id', test_id
        ).order('created_at', desc=True).execute()
        
        return response.data or []
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing sessions: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/admin/session/{session_id}/submissions", response_model=List[SubmissionResponse])
async def get_session_submissions(
    session_id: str,
    current_user: dict = Depends(require_role(["admin"]))
):
    """Get all submissions for a session (Admin)"""
    try:
        supabase = get_supabase_client()
        
        # Get submissions
        response = supabase.table('submissions').select('*').eq(
            'session_id', session_id
        ).execute()
        submissions = response.data or []

        if not submissions:
            return []

        # Collect unique question IDs
        question_ids = list({sub['question_id'] for sub in submissions if sub.get('question_id')})

        # Fetch all relevant questions in one query
        questions_response = supabase.table('questions').select('*').in_(
            'id', question_ids
        ).execute()
        questions_map = {q['id']: q for q in (questions_response.data or [])}

        # Attach full question object to each submission
        for sub in submissions:
            sub['question'] = questions_map.get(sub.get('question_id'))

        return submissions
        
    except Exception as e:
        logger.error(f"Error getting submissions: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/admin/session/{session_id}/review", response_model=TestSessionResponse)
async def review_session(
    session_id: str,
    review_data: TestSessionAdminReview,
    current_user: dict = Depends(require_role(["admin"]))
):
    """Admin review and approve/reject session"""
    try:
        supabase = get_supabase_client()
        
        update_data = {
            'admin_reviewed': True,
            'reviewed_by': current_user['id'],
            'reviewed_at': datetime.utcnow().isoformat(),
            'admin_comments': review_data.admin_comments,
            'final_status': review_data.final_status
        }
        
        response = supabase.table('test_sessions').update(update_data).eq(
            'id', session_id
        ).execute()
        
        return response.data[0] if response.data else None
        
    except Exception as e:
        logger.error(f"Error reviewing session: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/admin/submission/{submission_id}/grade", response_model=SubmissionResponse)
async def manual_grade_submission(
    submission_id: str,
    grading_data: ManualGrading,
    current_user: dict = Depends(require_role(["admin"]))
):
    """Manually grade descriptive answer"""
    try:
        # Grade submission
        grading_result = await grading_engine.grade_descriptive_manually(
            submission_id=submission_id,
            marks_obtained=grading_data.marks_obtained,
            grader_id=current_user['id'],
            feedback=grading_data.grader_feedback,
            notes=grading_data.grading_notes
        )
        
        # Update submission
        supabase = get_supabase_client()
        submission_response = supabase.table('submissions').select('session_id').eq(
            'id', submission_id
        ).single().execute()
        
        if submission_response.data:
            session_id = submission_response.data['session_id']
            
            # Filter grading result to only include columns that exist in submissions table
            submission_update_fields = {
                'status', 'is_correct', 'marks_obtained', 'max_marks', 
                'auto_graded', 'manually_graded', 'execution_output', 
                'execution_error', 'execution_time_ms', 'test_cases_passed', 
                'test_cases_total', 'grader_feedback', 'grading_notes', 
                'graded_by', 'graded_at', 'memory_used_mb'
            }
            filtered_result = {k: v for k, v in grading_result.items() if k in submission_update_fields}
            filtered_result['status'] = 'graded'  # Ensure status is set
            
            # Update submission with grading
            supabase.table('submissions').update(filtered_result).eq('id', submission_id).execute()
            
            # Recalculate session score
            await grading_engine.calculate_session_score(session_id)
        
        # Get updated submission
        final_submission = supabase.table('submissions').select('*').eq(
            'id', submission_id
        ).single().execute()
        
        return final_submission.data
        
    except Exception as e:
        logger.error(f"Error grading submission: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/admin/invitation/{invitation_id}/reset")
async def reset_attempt(
    invitation_id: str,
    reset_data: TestSessionResetRequest,
    current_user: dict = Depends(require_role(["admin"]))
):
    """Reset session to allow candidate to retake"""
    try:
        result = await session_manager.reset_session(
            invitation_id=invitation_id,
            admin_id=current_user['id'],
            reason=reset_data.reason
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Error resetting session: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/admin/candidate-history")
async def get_candidate_test_history(
    email: str,
    current_user: dict = Depends(require_role(["admin"]))
):
    """Return all test invitations and sessions for a candidate email (Admin)"""
    try:
        supabase = get_supabase_client()
        company_id = current_user.get("company_id")

        query = supabase.table('test_invitations').select('*').eq('candidate_email', email)
        if company_id:
            query = query.eq('company_id', company_id)

        invitations_resp = query.order('created_at', desc=True).execute()
        inv_list = invitations_resp.data or []

        result = []
        for inv in inv_list:
            # Fetch test metadata
            test_resp = supabase.table('tests').select(
                'id, title, duration_minutes, total_marks, passing_marks'
            ).eq('id', inv['test_id']).single().execute()

            # Fetch session if exists
            session_resp = supabase.table('test_sessions').select('*').eq(
                'invitation_id', inv['id']
            ).limit(1).execute()

            result.append({
                'invitation': inv,
                'test': test_resp.data,
                'session': session_resp.data[0] if session_resp.data else None,
            })

        return result

    except Exception as e:
        logger.error(f"Error fetching candidate history: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# ============================================
# Violation Clip Upload / Retrieval
# ============================================

def _extract_signed_url(result) -> str:
    """Handle both old-SDK (plain dict) and new-SDK (.data wrapper) supabase-py shapes."""
    if result is None:
        return ''
    # New SDK: result has a .data attribute (object or dict)
    if hasattr(result, 'data') and result.data:
        data = result.data
        if isinstance(data, dict):
            return data.get('signedUrl') or data.get('signedURL') or ''
        return getattr(data, 'signedUrl', None) or getattr(data, 'signedURL', None) or ''
    # Old SDK: result is a plain dict
    if isinstance(result, dict):
        return result.get('signedURL') or result.get('signedUrl') or ''
    return ''


@router.post("/{session_token}/violation-clip")
async def upload_violation_clip(
    session_token: str,
    clip: UploadFile = File(...),
    violation_type: str = Form(...),
    description: str = Form(default=""),
    occurred_at: str = Form(default=None),
):
    """Upload a short (~10s) violation clip for a test session (Public endpoint)"""
    try:
        supabase = SupabaseClient.get_service_client()

        # Resolve session
        session_res = supabase.table('test_sessions').select('id').eq(
            'session_token', session_token
        ).single().execute()
        if not session_res.data:
            raise HTTPException(status_code=404, detail="Session not found")

        session_id = session_res.data['id']

        # Upload video to Supabase Storage
        clip_bytes = await clip.read()
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        file_path = f"{session_id}/{violation_type}_{timestamp}.webm"

        supabase.storage.from_('violation-clips').upload(
            file_path,
            clip_bytes,
            file_options={"content-type": "video/webm", "upsert": "true"},
        )

        # Generate a signed URL (valid 7 days)
        try:
            signed = supabase.storage.from_('violation-clips').create_signed_url(
                file_path, 60 * 60 * 24 * 7
            )
            clip_url = _extract_signed_url(signed)
        except Exception:
            clip_url = ''

        # Persist metadata
        record = supabase.table('violation_clips').insert({
            'session_id': session_id,
            'violation_type': violation_type,
            'description': description,
            'clip_path': file_path,
            'clip_url': clip_url,
            'occurred_at': occurred_at or datetime.utcnow().isoformat(),
            'duration_seconds': 8,
        }).execute()

        return {"success": True, "clip_id": record.data[0]['id'] if record.data else None}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to upload violation clip: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/session/{session_id}/violation-clips")
async def get_violation_clips(
    session_id: str,
    current_user: dict = Depends(require_role(["admin"])),
):
    """Get all violation clips for a session (Admin) — refreshes signed URLs"""
    try:
        supabase = SupabaseClient.get_service_client()
        res = supabase.table('violation_clips').select('*').eq(
            'session_id', session_id
        ).order('occurred_at').execute()

        clips = res.data or []

        # Refresh signed URLs so they're always valid
        for clip in clips:
            if clip.get('clip_path'):
                try:
                    signed = supabase.storage.from_('violation-clips').create_signed_url(
                        clip['clip_path'], 60 * 60 * 24 * 7
                    )
                    refreshed = _extract_signed_url(signed)
                    if refreshed:
                        clip['clip_url'] = refreshed
                except Exception:
                    pass

        return clips

    except Exception as e:
        logger.error(f"Error fetching violation clips: {e}")
        raise HTTPException(status_code=500, detail=str(e))
