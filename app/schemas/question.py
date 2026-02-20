"""
Question schemas for the testing platform
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator
from enum import Enum


class QuestionType(str, Enum):
    sql = "sql"
    python = "python"
    javascript = "javascript"
    mcq = "mcq"
    descriptive = "descriptive"


class DifficultyLevel(str, Enum):
    easy = "easy"
    medium = "medium"
    hard = "hard"


class SubmissionStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    error = "error"
    timeout = "timeout"
    graded = "graded"


# ============================================
# Test Case Schemas (for coding questions)
# ============================================

class TestCase(BaseModel):
    input: Optional[str] = None
    expected_output: str
    is_hidden: bool = False
    marks: Optional[int] = None
    explanation: Optional[str] = None


# ============================================
# MCQ Option Schema
# ============================================

class MCQOption(BaseModel):
    id: str  # Unique identifier for the option
    text: str = Field(..., min_length=1, max_length=500)
    is_correct: bool


# ============================================
# Question Base Schemas
# ============================================

class QuestionBase(BaseModel):
    title: str = Field(..., min_length=5, max_length=300)
    description: str = Field(..., min_length=10)
    question_type: QuestionType
    difficulty: DifficultyLevel = DifficultyLevel.medium
    marks: int = Field(..., gt=0, le=100)
    tags: Optional[List[str]] = None
    is_active: bool = True


class CodingQuestionFields(BaseModel):
    """Fields specific to coding questions (SQL, Python, JavaScript)"""
    code_template: Optional[str] = None
    test_cases: List[TestCase] = Field(..., min_length=1)
    time_limit: int = Field(default=30, gt=0, le=300)  # seconds
    memory_limit: int = Field(default=512, gt=0, le=2048)  # MB


class SQLQuestionFields(CodingQuestionFields):
    """Additional fields specific to SQL questions"""
    sql_schema: str = Field(..., min_length=10)
    sql_seed_data: str = Field(..., min_length=10)
    expected_query_result: Optional[Any] = None  # List of dicts (query result rows)


class MCQQuestionFields(BaseModel):
    """Fields specific to MCQ questions"""
    mcq_options: List[MCQOption] = Field(..., min_length=2, max_length=10)
    is_multiple_correct: bool = False

    @field_validator('mcq_options')
    @classmethod
    def validate_options(cls, options: List[MCQOption]) -> List[MCQOption]:
        if not any(opt.is_correct for opt in options):
            raise ValueError("At least one option must be marked as correct")
        return options


class DescriptiveQuestionFields(BaseModel):
    """Fields specific to descriptive questions"""
    ideal_answer: Optional[str] = None
    grading_rubric: Optional[str] = None


# ============================================
# Question Create/Update Schemas
# ============================================

class QuestionCreate(QuestionBase):
    # For coding questions
    code_template: Optional[str] = None
    test_cases: Optional[List[TestCase]] = None
    time_limit: Optional[int] = Field(default=30, gt=0, le=300)
    memory_limit: Optional[int] = Field(default=512, gt=0, le=2048)
    
    # For SQL questions
    sql_schema: Optional[str] = None
    sql_seed_data: Optional[str] = None
    expected_query_result: Optional[Any] = None  # Can be list of dicts or single dict
    
    # For MCQ questions
    mcq_options: Optional[List[MCQOption]] = None
    is_multiple_correct: Optional[bool] = False
    
    # For descriptive questions
    ideal_answer: Optional[str] = None
    grading_rubric: Optional[str] = None

    @field_validator('test_cases')
    @classmethod
    def validate_test_cases(cls, test_cases, info):
        question_type = info.data.get('question_type')
        # Only Python and JavaScript require test_cases (SQL uses expected_query_result)
        if question_type in ['python', 'javascript'] and not test_cases:
            raise ValueError(f"Test cases are required for {question_type} questions")
        return test_cases

    @field_validator('sql_schema')
    @classmethod
    def validate_sql_schema(cls, sql_schema, info):
        question_type = info.data.get('question_type')
        if question_type == 'sql' and not sql_schema:
            raise ValueError("SQL schema is required for SQL questions")
        return sql_schema

    @field_validator('expected_query_result')
    @classmethod
    def validate_expected_query_result(cls, expected_result, info):
        question_type = info.data.get('question_type')
        if question_type == 'sql' and not expected_result:
            raise ValueError("Expected query result is required for SQL questions")
        return expected_result

    @field_validator('mcq_options')
    @classmethod
    def validate_mcq_options(cls, mcq_options, info):
        question_type = info.data.get('question_type')
        if question_type == 'mcq':
            if not mcq_options or len(mcq_options) < 2:
                raise ValueError("At least 2 options are required for MCQ questions")
            if not any(opt.is_correct for opt in mcq_options):
                raise ValueError("At least one option must be marked as correct")
        return mcq_options


class QuestionUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=5, max_length=300)
    description: Optional[str] = Field(None, min_length=10)
    difficulty: Optional[DifficultyLevel] = None
    marks: Optional[int] = Field(None, gt=0, le=100)
    tags: Optional[List[str]] = None
    is_active: Optional[bool] = None
    
    # Coding fields
    code_template: Optional[str] = None
    test_cases: Optional[List[TestCase]] = None
    time_limit: Optional[int] = Field(None, gt=0, le=300)
    memory_limit: Optional[int] = Field(None, gt=0, le=2048)
    
    # SQL fields
    sql_schema: Optional[str] = None
    sql_seed_data: Optional[str] = None
    expected_query_result: Optional[Any] = None  # Can be list of dicts or single dict
    
    # MCQ fields
    mcq_options: Optional[List[MCQOption]] = None
    is_multiple_correct: Optional[bool] = None
    
    # Descriptive fields
    ideal_answer: Optional[str] = None
    grading_rubric: Optional[str] = None


class QuestionResponse(QuestionBase):
    id: str
    code_template: Optional[str] = None
    test_cases: Optional[List[TestCase]] = None
    time_limit: Optional[int] = None
    memory_limit: Optional[int] = None
    sql_schema: Optional[str] = None
    sql_seed_data: Optional[str] = None
    expected_query_result: Optional[Any] = None  # Can be list of dicts or single dict
    mcq_options: Optional[List[MCQOption]] = None
    is_multiple_correct: Optional[bool] = None
    ideal_answer: Optional[str] = None
    grading_rubric: Optional[str] = None
    created_by: str
    company_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class QuestionForCandidate(BaseModel):
    """Sanitized question for candidates (hide answers/solutions)"""
    id: str
    title: str
    description: str
    question_type: QuestionType
    difficulty: DifficultyLevel
    marks: int
    code_template: Optional[str] = None
    time_limit: Optional[int] = None
    memory_limit: Optional[int] = None
    sql_schema: Optional[str] = None
    sql_seed_data: Optional[str] = None
    mcq_options: Optional[List[Dict[str, Any]]] = None  # Without is_correct flag
    is_multiple_correct: Optional[bool] = None


# ============================================
# Submission Schemas
# ============================================

class SubmissionCreate(BaseModel):
    question_id: str
    code_answer: Optional[str] = None
    mcq_selected_options: Optional[List[str]] = None  # List of option IDs
    text_answer: Optional[str] = None

    @field_validator('mcq_selected_options')
    @classmethod
    def validate_mcq_selections(cls, selections):
        if selections and len(selections) == 0:
            raise ValueError("At least one option must be selected for MCQ")
        return selections


class SubmissionUpdate(BaseModel):
    code_answer: Optional[str] = None
    mcq_selected_options: Optional[List[str]] = None
    text_answer: Optional[str] = None


class ExecutionResult(BaseModel):
    """Result from code execution"""
    output: Optional[str] = None
    error: Optional[str] = None
    execution_time_ms: Optional[int] = None
    memory_used_mb: Optional[float] = None
    test_cases_passed: int = 0
    test_cases_total: int = 0
    test_results: Optional[List[Dict[str, Any]]] = None


class SubmissionResponse(BaseModel):
    id: str
    session_id: str
    question_id: str
    question_type: QuestionType
    code_answer: Optional[str] = None
    mcq_selected_options: Optional[List[str]] = None
    text_answer: Optional[str] = None
    execution_output: Optional[str] = None
    execution_error: Optional[str] = None
    execution_time_ms: Optional[int] = None
    memory_used_mb: Optional[float] = None
    test_cases_passed: int = 0
    test_cases_total: int = 0
    status: SubmissionStatus
    is_correct: Optional[bool] = None
    marks_obtained: float = 0
    max_marks: int
    auto_graded: bool = False
    manually_graded: bool = False
    graded_by: Optional[str] = None
    graded_at: Optional[datetime] = None
    grader_feedback: Optional[str] = None
    grading_notes: Optional[str] = None
    submitted_at: datetime
    updated_at: Optional[datetime] = None
    question: Optional[Dict[str, Any]] = None  # Full question details for grading

    @field_validator('test_cases_passed', 'test_cases_total', 'marks_obtained', mode='before')
    @classmethod
    def convert_none_to_zero(cls, v):
        """Convert None to 0 for numeric fields (handles legacy NULL data)"""
        return 0 if v is None else v

    class Config:
        from_attributes = True


# ============================================
# Manual Grading Schemas
# ============================================

class ManualGrading(BaseModel):
    marks_obtained: float = Field(..., ge=0)
    grader_feedback: Optional[str] = None
    grading_notes: Optional[str] = None

    @field_validator('marks_obtained')
    @classmethod
    def validate_marks(cls, marks):
        if marks < 0:
            raise ValueError("Marks cannot be negative")
        return marks


class GradingLogResponse(BaseModel):
    id: str
    submission_id: str
    session_id: str
    question_id: str
    grading_type: str
    marks_before: Optional[float] = None
    marks_after: Optional[float] = None
    graded_by: Optional[str] = None
    grading_details: Optional[Dict[str, Any]] = None
    comments: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ============================================
# Code Execution Request
# ============================================

class CodeExecutionRequest(BaseModel):
    question_id: str
    code: str
    language: str = Field(..., pattern='^(sql|python|javascript)$')
    test_run: bool = False  # If True, run test cases; if False, just execute


class CodeExecutionResponse(BaseModel):
    success: bool
    output: Optional[str] = None
    error: Optional[str] = None
    execution_time_ms: Optional[int] = None
    memory_used_mb: Optional[float] = None
    test_cases_passed: int = 0
    test_cases_total: int = 0
    test_results: Optional[List[Dict[str, Any]]] = None
    is_correct: bool = False
    marks_obtained: float = 0
