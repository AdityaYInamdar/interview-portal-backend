"""
Tests API endpoints
CRUD operations for tests, adding questions to tests, and test management
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List, Optional
from app.schemas.test import (
    TestCreate, TestUpdate, TestResponse, TestWithQuestions,
    TestQuestionAdd, TestQuestionBulkAdd, TestQuestionReorderPayload,
    TestQuestionResponse, TestStatistics
)
from app.core.supabase import get_supabase_client
from app.core.security import get_current_user, require_role
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tests", tags=["tests"])


# ============================================
# Test CRUD Operations
# ============================================

@router.post("", response_model=TestResponse, status_code=status.HTTP_201_CREATED)
async def create_test(
    test_data: TestCreate,
    current_user: dict = Depends(require_role(["admin"]))
):
    """Create a new test (Admin only)"""
    try:
        supabase = get_supabase_client()
        
        data = test_data.model_dump()
        data['created_by'] = current_user['id']
        data['company_id'] = current_user['company_id']
        data['total_marks'] = 0  # Will be calculated when questions are added
        
        response = supabase.table('tests').insert(data).execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create test"
            )
        
        test = response.data[0]
        test['question_count'] = 0
        
        return test
        
    except Exception as e:
        logger.error(f"Error creating test: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("", response_model=List[TestResponse])
async def list_tests(
    is_published: Optional[bool] = None,
    is_active: Optional[bool] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: dict = Depends(get_current_user)
):
    """List all tests for the user's company"""
    try:
        supabase = get_supabase_client()
        
        query = supabase.table('tests').select(
            '*, test_questions(question_id)',
            count='exact'
        ).eq('company_id', current_user['company_id'])
        
        if is_published is not None:
            query = query.eq('is_published', is_published)
        
        if is_active is not None:
            query = query.eq('is_active', is_active)
        
        query = query.order('created_at', desc=True).range(skip, skip + limit - 1)
        
        response = query.execute()
        
        tests = response.data or []
        
        # Add question count to each test
        for test in tests:
            # Count the actual test_questions returned
            test['question_count'] = len(test.get('test_questions', []))
            # Remove the test_questions array from response (we only need the count)
            test.pop('test_questions', None)
        
        return tests
        
    except Exception as e:
        logger.error(f"Error listing tests: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/{test_id}", response_model=TestWithQuestions)
async def get_test(
    test_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get test details with questions"""
    try:
        supabase = get_supabase_client()
        
        # Get test with questions
        test_response = supabase.table('tests').select(
            '*, test_questions(*, questions(*))'
        ).eq('id', test_id).eq('company_id', current_user['company_id']).single().execute()
        
        if not test_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Test not found"
            )
        
        test = test_response.data
        
        # Format questions
        test_questions = test.get('test_questions', [])
        test['questions'] = [
            {
                'id': tq['questions']['id'],
                'title': tq['questions']['title'],
                'question_type': tq['questions']['question_type'],
                'difficulty': tq['questions']['difficulty'],
                'marks': tq['questions']['marks'],
                'question_order': tq['question_order'],
                'is_mandatory': tq['is_mandatory']
            }
            for tq in test_questions
        ]
        
        test['question_count'] = len(test['questions'])
        
        return test
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting test {test_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.put("/{test_id}", response_model=TestResponse)
async def update_test(
    test_id: str,
    test_data: TestUpdate,
    current_user: dict = Depends(require_role(["admin"]))
):
    """Update test (Admin only)"""
    try:
        supabase = get_supabase_client()
        
        # Verify ownership
        test_check = supabase.table('tests').select('id').eq(
            'id', test_id
        ).eq('company_id', current_user['company_id']).single().execute()
        
        if not test_check.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Test not found"
            )
        
        # Update test
        update_data = test_data.model_dump(exclude_unset=True)
        
        response = supabase.table('tests').update(update_data).eq('id', test_id).execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update test"
            )
        
        return response.data[0]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating test {test_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.delete("/{test_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_test(
    test_id: str,
    current_user: dict = Depends(require_role(["admin"]))
):
    """Delete test (Admin only)"""
    try:
        supabase = get_supabase_client()
        
        # Verify ownership
        test_check = supabase.table('tests').select('id').eq(
            'id', test_id
        ).eq('company_id', current_user['company_id']).single().execute()
        
        if not test_check.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Test not found"
            )
        
        # Delete test (cascade will handle related records)
        supabase.table('tests').delete().eq('id', test_id).execute()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting test {test_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# ============================================
# Test-Question Management
# ============================================

@router.post("/{test_id}/questions", response_model=TestQuestionResponse)
async def add_question_to_test(
    test_id: str,
    question_data: TestQuestionAdd,
    current_user: dict = Depends(require_role(["admin"]))
):
    """Add a question to a test"""
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
        
        # Verify question exists and belongs to company
        question_check = supabase.table('questions').select('id').eq(
            'id', question_data.question_id
        ).eq('company_id', current_user['company_id']).single().execute()
        
        if not question_check.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Question not found"
            )
        
        # Add question to test
        data = question_data.model_dump()
        data['test_id'] = test_id
        
        response = supabase.table('test_questions').insert(data).execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to add question to test"
            )
        
        # Total marks will be auto-updated by trigger
        
        return response.data[0]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding question to test {test_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/{test_id}/questions/bulk")
async def bulk_add_questions_to_test(
    test_id: str,
    payload: TestQuestionBulkAdd,
    current_user: dict = Depends(require_role(["admin"]))
):
    """Add multiple questions to a test in one request"""
    try:
        supabase = get_supabase_client()

        # Verify test ownership
        test_check = supabase.table('tests').select('id').eq(
            'id', test_id
        ).eq('company_id', current_user['company_id']).single().execute()
        if not test_check.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test not found")

        # Find which question_ids are already in the test to avoid duplicates
        existing_resp = supabase.table('test_questions').select('question_id').eq('test_id', test_id).execute()
        existing_ids = {row['question_id'] for row in (existing_resp.data or [])}

        # Validate all question IDs belong to the company
        valid_resp = supabase.table('questions').select('id').eq(
            'company_id', current_user['company_id']
        ).in_('id', payload.question_ids).execute()
        valid_ids = {row['id'] for row in (valid_resp.data or [])}

        novel_ids = [qid for qid in payload.question_ids if qid in valid_ids and qid not in existing_ids]

        if not novel_ids:
            return {'added': 0, 'skipped': len(payload.question_ids), 'message': 'All selected questions are already in the test'}

        # Determine starting order
        order_resp = supabase.table('test_questions').select('question_order').eq('test_id', test_id).order('question_order', desc=True).limit(1).execute()
        next_order = (order_resp.data[0]['question_order'] + 1) if order_resp.data else 1

        rows = [
            {
                'test_id': test_id,
                'question_id': qid,
                'question_order': next_order + i,
                'is_mandatory': payload.is_mandatory,
            }
            for i, qid in enumerate(novel_ids)
        ]
        supabase.table('test_questions').insert(rows).execute()

        skipped = len(payload.question_ids) - len(novel_ids)
        return {
            'added': len(novel_ids),
            'skipped': skipped,
            'message': f'Added {len(novel_ids)} question(s)' + (f', skipped {skipped} already in test' if skipped else ''),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error bulk-adding questions to test {test_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.put("/{test_id}/questions/reorder")
async def reorder_test_questions(
    test_id: str,
    payload: TestQuestionReorderPayload,
    current_user: dict = Depends(require_role(["admin"]))
):
    """Update the question_order for every question in a test in one call"""
    try:
        supabase = get_supabase_client()

        # Verify test ownership
        test_check = supabase.table('tests').select('id').eq(
            'id', test_id
        ).eq('company_id', current_user['company_id']).single().execute()
        if not test_check.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test not found")

        # Two-pass update to avoid unique constraint violations on (test_id, question_order):
        # Pass 1 — shift every order to a safe temporary value (offset by 100000)
        for item in payload.questions:
            supabase.table('test_questions') \
                .update({'question_order': item.question_order + 100000}) \
                .eq('test_id', test_id) \
                .eq('question_id', item.question_id) \
                .execute()

        # Pass 2 — set the real target order values
        for item in payload.questions:
            supabase.table('test_questions') \
                .update({'question_order': item.question_order}) \
                .eq('test_id', test_id) \
                .eq('question_id', item.question_id) \
                .execute()

        return {'updated': len(payload.questions)}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reordering questions in test {test_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.delete("/{test_id}/questions/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_question_from_test(
    test_id: str,
    question_id: str,
    current_user: dict = Depends(require_role(["admin"]))
):
    """Remove a question from a test"""
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
        
        # Remove question
        supabase.table('test_questions').delete().eq(
            'test_id', test_id
        ).eq('question_id', question_id).execute()
        
        # Total marks will be auto-updated by trigger
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing question from test: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# ============================================
# Test Publishing
# ============================================

@router.post("/{test_id}/publish", response_model=TestResponse)
async def publish_test(
    test_id: str,
    current_user: dict = Depends(require_role(["admin"]))
):
    """Publish a test (make it available for invitations)"""
    try:
        supabase = get_supabase_client()
        
        # Verify test ownership and has questions
        test_response = supabase.table('tests').select(
            '*, test_questions(count)'
        ).eq('id', test_id).eq('company_id', current_user['company_id']).single().execute()
        
        if not test_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Test not found"
            )
        
        test = test_response.data
        
        if len(test.get('test_questions', [])) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot publish test without questions"
            )
        
        # Publish test
        from datetime import datetime
        response = supabase.table('tests').update({
            'is_published': True,
            'published_at': datetime.utcnow().isoformat()
        }).eq('id', test_id).execute()
        
        return response.data[0]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error publishing test {test_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/{test_id}/unpublish", response_model=TestResponse)
async def unpublish_test(
    test_id: str,
    current_user: dict = Depends(require_role(["admin"]))
):
    """Unpublish a test"""
    try:
        supabase = get_supabase_client()
        
        # Verify ownership
        test_check = supabase.table('tests').select('id').eq(
            'id', test_id
        ).eq('company_id', current_user['company_id']).single().execute()
        
        if not test_check.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Test not found"
            )
        
        # Unpublish
        response = supabase.table('tests').update({
            'is_published': False
        }).eq('id', test_id).execute()
        
        return response.data[0]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error unpublishing test: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# ============================================
# Test Statistics
# ============================================

@router.get("/{test_id}/statistics", response_model=TestStatistics)
async def get_test_statistics(
    test_id: str,
    current_user: dict = Depends(require_role(["admin"]))
):
    """Get statistics for a test"""
    try:
        supabase = get_supabase_client()
        
        # Verify ownership
        test_check = supabase.table('tests').select('id').eq(
            'id', test_id
        ).eq('company_id', current_user['company_id']).single().execute()
        
        if not test_check.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Test not found"
            )
        
        # Get invitations count
        invitations_response = supabase.table('test_invitations').select(
            'id', count='exact'
        ).eq('test_id', test_id).execute()
        
        total_invitations = invitations_response.count or 0
        
        # Get sessions stats
        sessions_response = supabase.table('test_sessions').select(
            'status, total_marks_obtained, total_marks, started_at, ended_at'
        ).eq('test_id', test_id).execute()
        
        sessions = sessions_response.data or []
        
        total_attempts = len(sessions)
        completed_attempts = len([s for s in sessions if s.get('status') == 'completed'])
        in_progress_attempts = len([s for s in sessions if s.get('status') == 'active'])
        
        # Calculate averages
        completed_sessions = [s for s in sessions if s.get('status') == 'completed']
        
        if completed_sessions:
            avg_score = sum(
                float(s.get('total_marks_obtained', 0)) for s in completed_sessions
            ) / len(completed_sessions)
            
            # Get test passing marks
            test_data = supabase.table('tests').select('passing_marks').eq('id', test_id).single().execute()
            passing_marks = test_data.data.get('passing_marks', 0) if test_data.data else 0
            
            passed_count = len([
                s for s in completed_sessions 
                if float(s.get('total_marks_obtained', 0)) >= passing_marks
            ])
            pass_rate = (passed_count / len(completed_sessions)) * 100
            
            # Calculate average completion time
            times = []
            for s in completed_sessions:
                if s.get('started_at') and s.get('ended_at'):
                    from datetime import datetime
                    start = datetime.fromisoformat(s['started_at'].replace('Z', '+00:00'))
                    end = datetime.fromisoformat(s['ended_at'].replace('Z', '+00:00'))
                    duration_minutes = (end - start).total_seconds() / 60
                    times.append(duration_minutes)
            
            avg_time = sum(times) / len(times) if times else None
        else:
            avg_score = None
            pass_rate = None
            avg_time = None
        
        return {
            'total_invitations': total_invitations,
            'total_attempts': total_attempts,
            'completed_attempts': completed_attempts,
            'in_progress_attempts': in_progress_attempts,
            'average_score': round(avg_score, 2) if avg_score else None,
            'pass_rate': round(pass_rate, 2) if pass_rate else None,
            'average_completion_time_minutes': round(avg_time, 2) if avg_time else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting test statistics: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
