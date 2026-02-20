"""
Code execution API endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from typing import Optional, List
from pydantic import BaseModel, Field

from app.core.security import get_current_user_token
from app.services.code_execution_service import code_execution_service

router = APIRouter(prefix="/code", tags=["Code Execution"])


class CodeExecuteRequest(BaseModel):
    """Request model for code execution."""
    code: str = Field(..., description="Source code to execute")
    language: str = Field(..., description="Programming language")
    stdin: Optional[str] = Field(None, description="Standard input for the program")
    args: Optional[List[str]] = Field(None, description="Command-line arguments")


class CodeExecuteResponse(BaseModel):
    """Response model for code execution."""
    success: bool
    output: str
    error: str
    stdout: str
    stderr: str
    runtime: float
    language: str
    version: str
    exit_code: Optional[int] = None


class LanguageInfo(BaseModel):
    """Programming language information."""
    language: str
    version: str
    aliases: List[str] = []


@router.post("/execute", response_model=CodeExecuteResponse)
async def execute_code(
    request: CodeExecuteRequest,
    current_user: dict = Depends(get_current_user_token)
):
    """
    Execute code in specified programming language.
    
    Supports 20+ languages including:
    - JavaScript, Python, Java, C++, C, C#
    - Go, Rust, Ruby, PHP, TypeScript
    - Swift, Kotlin, Scala, and more
    
    Returns:
        Execution results with output, errors, and runtime information
    """
    try:
        result = await code_execution_service.execute_code(
            code=request.code,
            language=request.language,
            stdin=request.stdin,
            args=request.args
        )
        
        return CodeExecuteResponse(**result)
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Code execution failed: {str(e)}"
        )


@router.get("/languages", response_model=List[LanguageInfo])
async def get_supported_languages(
    current_user: dict = Depends(get_current_user_token)
):
    """
    Get list of supported programming languages.
    
    Returns:
        List of available languages with their versions
    """
    try:
        languages = await code_execution_service.get_supported_languages()
        return languages
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch languages: {str(e)}"
        )
