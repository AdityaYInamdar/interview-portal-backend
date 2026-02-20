"""
Questions API endpoints
CRUD for questions (SQL, Python, JavaScript, MCQ, Descriptive)
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List, Optional
from app.schemas.question import (
    QuestionCreate, QuestionUpdate, QuestionResponse,
    QuestionType, DifficultyLevel
)
from app.core.supabase import get_supabase_client
from app.core.security import get_current_user, require_role
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/questions", tags=["questions"])


@router.post("", response_model=QuestionResponse, status_code=status.HTTP_201_CREATED)
async def create_question(
    question_data: QuestionCreate,
    current_user: dict = Depends(require_role(["admin"]))
):
    """Create a new question (Admin only)"""
    try:
        supabase = get_supabase_client()
        
        data = question_data.model_dump(mode='json')
        data['created_by'] = current_user['id']
        data['company_id'] = current_user['company_id']
        
        response = supabase.table('questions').insert(data).execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create question"
            )
        
        return response.data[0]
        
    except Exception as e:
        logger.error(f"Error creating question: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("", response_model=List[QuestionResponse])
async def list_questions(
    question_type: Optional[QuestionType] = None,
    difficulty: Optional[DifficultyLevel] = None,
    is_active: Optional[bool] = None,
    search: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: dict = Depends(get_current_user)
):
    """List questions with filters"""
    try:
        supabase = get_supabase_client()
        
        query = supabase.table('questions').select('*', count='exact').eq(
            'company_id', current_user['company_id']
        )
        
        if question_type:
            query = query.eq('question_type', question_type.value)
        
        if difficulty:
            query = query.eq('difficulty', difficulty.value)
        
        if is_active is not None:
            query = query.eq('is_active', is_active)
        
        if search:
            query = query.ilike('title', f'%{search}%')
        
        query = query.order('created_at', desc=True).range(skip, skip + limit - 1)
        
        response = query.execute()
        
        return response.data or []
        
    except Exception as e:
        logger.error(f"Error listing questions: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/{question_id}", response_model=QuestionResponse)
async def get_question(
    question_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get question details"""
    try:
        supabase = get_supabase_client()
        
        response = supabase.table('questions').select('*').eq(
            'id', question_id
        ).eq('company_id', current_user['company_id']).single().execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Question not found"
            )
        
        return response.data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting question: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.put("/{question_id}", response_model=QuestionResponse)
async def update_question(
    question_id: str,
    question_data: QuestionUpdate,
    current_user: dict = Depends(require_role(["admin"]))
):
    """Update question"""
    try:
        supabase = get_supabase_client()
        
        # Verify ownership
        check = supabase.table('questions').select('id').eq(
            'id', question_id
        ).eq('company_id', current_user['company_id']).single().execute()
        
        if not check.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Question not found"
            )
        
        update_data = question_data.model_dump(exclude_unset=True, mode='json')
        
        response = supabase.table('questions').update(update_data).eq('id', question_id).execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update question"
            )
        
        return response.data[0]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating question: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.delete("/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_question(
    question_id: str,
    current_user: dict = Depends(require_role(["admin"]))
):
    """Delete question"""
    try:
        supabase = get_supabase_client()
        
        # Verify ownership
        check = supabase.table('questions').select('id').eq(
            'id', question_id
        ).eq('company_id', current_user['company_id']).single().execute()
        
        if not check.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Question not found"
            )
        
        supabase.table('questions').delete().eq('id', question_id).execute()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting question: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
