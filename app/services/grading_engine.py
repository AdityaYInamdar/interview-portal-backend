"""
Grading Engine Service
Handles automatic grading for coding (SQL, Python, JavaScript) and MCQ questions,
and supports manual grading for descriptive questions
"""
from typing import Dict, Any, List, Optional
from datetime import datetime
import json
import logging
from app.services.code_execution_service import CodeExecutionService
from app.core.supabase import get_supabase_client, SupabaseClient

logger = logging.getLogger(__name__)


class GradingEngine:
    """Central grading engine for all question types"""

    def __init__(self):
        self.supabase = get_supabase_client()  # Regular client
        self.service_supabase = SupabaseClient.get_service_client()  # Service client (bypasses RLS)
        self.code_executor = CodeExecutionService()

    async def grade_submission(
        self,
        submission_id: str,
        question_data: Dict[str, Any],
        answer_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Grade a submission based on question type
        Returns grading result with marks, feedback, and details
        """
        question_type = question_data.get('question_type')

        if question_type == 'mcq':
            result = await self._grade_mcq(question_data, answer_data)
        elif question_type in ['sql', 'python', 'javascript']:
            result = await self._grade_coding(question_data, answer_data, question_type)
        elif question_type == 'descriptive':
            result = self._grade_descriptive_pending()
        else:
            raise ValueError(f"Unsupported question type: {question_type}")

        # Log the grading
        await self._log_grading(submission_id, result)

        return result

    # ============================================
    # MCQ Grading
    # ============================================

    async def _grade_mcq(
        self,
        question_data: Dict[str, Any],
        answer_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Grade MCQ question by comparing selected options with correct answers"""
        mcq_options = question_data.get('mcq_options') or []
        selected_options = answer_data.get('mcq_selected_options') or []
        max_marks = question_data.get('marks', 0)
        is_multiple_correct = question_data.get('is_multiple_correct', False)

        # Extract correct option IDs
        correct_options = {opt['id'] for opt in mcq_options if opt.get('is_correct')}
        selected_set = set(selected_options)

        # Calculate correctness
        if is_multiple_correct:
            # Partial marking for multiple correct
            total_correct = len(correct_options)
            correctly_selected = len(selected_set.intersection(correct_options))
            incorrectly_selected = len(selected_set.difference(correct_options))
            
            # Scoring: +points for correct, -points for wrong
            marks_per_option = max_marks / total_correct
            marks_obtained = max(0, (correctly_selected * marks_per_option) - 
                               (incorrectly_selected * marks_per_option))
            
            is_correct = selected_set == correct_options
        else:
            # Single correct - all or nothing
            is_correct = selected_set == correct_options
            marks_obtained = max_marks if is_correct else 0

        return {
            'grading_type': 'auto',
            'is_correct': is_correct,
            'marks_obtained': round(marks_obtained, 2),
            'max_marks': max_marks,
            'auto_graded': True,
            'status': 'graded',
            'grading_details': {
                'correct_options': list(correct_options),
                'selected_options': selected_options,
                'is_multiple_correct': is_multiple_correct,
                'explanation': self._generate_mcq_feedback(
                    correct_options, selected_set, is_correct
                )
            }
        }

    def _generate_mcq_feedback(
        self,
        correct: set,
        selected: set,
        is_correct: bool
    ) -> str:
        """Generate feedback for MCQ answer"""
        if is_correct:
            return "Correct! All answers selected are right."
        
        missed = correct - selected
        wrong = selected - correct
        
        feedback_parts = []
        if wrong:
            feedback_parts.append(f"Incorrect options selected: {len(wrong)}")
        if missed:
            feedback_parts.append(f"Correct options missed: {len(missed)}")
        
        return " | ".join(feedback_parts)

    # ============================================
    # Coding Question Grading
    # ============================================

    async def _grade_coding(
        self,
        question_data: Dict[str, Any],
        answer_data: Dict[str, Any],
        language: str
    ) -> Dict[str, Any]:
        """Grade coding question by running test cases"""
        code = answer_data.get('code_answer', '')
        test_cases = question_data.get('test_cases') or []  # Ensure it's a list, not None
        max_marks = question_data.get('marks', 0)
        time_limit = question_data.get('time_limit', 30)

        if not code or not code.strip():
            return {
                'grading_type': 'auto',
                'is_correct': False,
                'marks_obtained': 0,
                'max_marks': max_marks,
                'auto_graded': True,
                'status': 'graded',
                'execution_error': 'No code provided',
                'test_cases_passed': 0,
                'test_cases_total': len(test_cases)
            }

        # For SQL, need special handling
        if language == 'sql':
            return await self._grade_sql(question_data, code, test_cases, max_marks)

        # For Python/JavaScript, run against test cases
        return await self._grade_general_coding(
            code, language, test_cases, max_marks, time_limit
        )

    async def _grade_sql(
        self,
        question_data: Dict[str, Any],
        query: str,
        test_cases: List[Dict],
        max_marks: int
    ) -> Dict[str, Any]:
        """Grade SQL query by running against schema and comparing results"""
        # Ensure test_cases is a list (SQL questions don't use test_cases)
        test_cases = test_cases or []
        
        sql_schema = question_data.get('sql_schema', '')
        sql_seed_data = question_data.get('sql_seed_data', '')
        
        try:
            # Execute SQL with schema and seed data
            execution_result = await self.code_executor.execute_sql_with_schema(
                schema=sql_schema,
                seed_data=sql_seed_data,
                query=query
            )

            if not execution_result.get('success'):
                error_msg = execution_result.get('error', 'Execution failed')
                return {
                    'grading_type': 'auto',
                    'is_correct': False,
                    'marks_obtained': 0,
                    'max_marks': max_marks,
                    'auto_graded': True,
                    'status': 'error',
                    'execution_output': error_msg,  # Include output for consistent display
                    'execution_error': error_msg,
                    'execution_time_ms': execution_result.get('runtime', 0),
                    'test_cases_passed': 0,
                    'test_cases_total': len(test_cases)
                }

            # Compare output with expected results
            query_result = execution_result.get('output')
            expected_result = question_data.get('expected_query_result')
            
            logger.info(f"[SQL_GRADE] Query result length: {len(query_result) if query_result else 0}, Expected length: {len(expected_result) if expected_result else 0}")

            # Simple comparison (can be enhanced with fuzzy matching)
            is_correct = self._compare_sql_results(query_result, expected_result)
            marks_obtained = max_marks if is_correct else 0

            return {
                'grading_type': 'auto',
                'is_correct': is_correct,
                'marks_obtained': marks_obtained,
                'max_marks': max_marks,
                'auto_graded': True,
                'status': 'graded',
                'execution_output': query_result,
                'execution_time_ms': execution_result.get('runtime', 0),
                'test_cases_passed': 1 if is_correct else 0,
                'test_cases_total': 1,
                'grading_details': {
                    'expected': expected_result,
                    'actual': query_result,
                    'match': is_correct
                }
            }

        except Exception as e:
            logger.error(f"SQL grading error: {str(e)}")
            error_msg = f"SQL Execution Error: {str(e)}"
            return {
                'grading_type': 'auto',
                'is_correct': False,
                'marks_obtained': 0,
                'max_marks': max_marks,
                'auto_graded': True,
                'status': 'error',
                'execution_output': error_msg,  # Include output for consistent display
                'execution_error': error_msg,
                'execution_time_ms': 0,
                'test_cases_passed': 0,
                'test_cases_total': len(test_cases)
            }

    async def _grade_general_coding(
        self,
        code: str,
        language: str,
        test_cases: List[Dict],
        max_marks: int,
        time_limit: int
    ) -> Dict[str, Any]:
        """Grade Python/JavaScript code against test cases"""
        test_results = []
        passed_count = 0
        total_marks_scored = 0
        total_execution_time = 0
        
        # First, run the original code as-is to show user output (with their print statements)
        original_output = ""
        try:
            original_exec = await self.code_executor.execute_code(
                code=code,
                language=language,
                stdin=''
            )
            original_output = original_exec.get('output', '')
        except Exception as e:
            logger.error(f"Error running original code: {str(e)}")
            original_output = f"Error: {str(e)}"
        
        # If no test cases, just return the execution output
        if not test_cases or len(test_cases) == 0:
            return {
                'grading_type': 'auto',
                'is_correct': False,
                'marks_obtained': 0,
                'max_marks': max_marks,
                'auto_graded': False,
                'status': 'executed',
                'execution_output': original_output,
                'execution_error': original_exec.get('error') if 'original_exec' in locals() else None,
                'execution_time_ms': original_exec.get('runtime', 0) if 'original_exec' in locals() else 0,
                'test_cases_passed': 0,
                'test_cases_total': 0
            }

        # Calculate marks per test case (distribute equally if not specified)
        marks_per_test = max_marks / len(test_cases) if test_cases else 0
        
        for idx, test_case in enumerate(test_cases):
            test_input = test_case.get('input', '')
            expected_output = test_case.get('expected_output', '').strip()
            # Use specified marks or distribute equally across all test cases
            test_marks = test_case.get('marks', marks_per_test)
            is_hidden = test_case.get('is_hidden', False)

            try:
                # For Python/JavaScript, wrap code to call the function with test input
                wrapped_code = self._wrap_code_for_testing(code, test_input, language)
                
                # Execute wrapped code
                exec_result = await self.code_executor.execute_code(
                    code=wrapped_code,
                    language=language,
                    stdin=''
                )

                success = exec_result.get('success', False)
                actual_output = exec_result.get('output', '').strip()
                error = exec_result.get('error')
                runtime = exec_result.get('runtime', 0)

                total_execution_time += runtime

                # Check if execution succeeded
                if not success or error:
                    test_results.append({
                        'test_case': idx + 1,
                        'passed': False,
                        'input': test_input if not is_hidden else '[Hidden]',
                        'expected': expected_output if not is_hidden else '[Hidden]',
                        'actual': error or 'Execution failed',
                        'error': error,
                        'marks': 0,
                        'max_marks': test_marks
                    })
                    continue

                # Compare output
                is_match = self._compare_outputs(actual_output, expected_output)

                if is_match:
                    passed_count += 1
                    total_marks_scored += test_marks

                test_results.append({
                    'test_case': idx + 1,
                    'passed': is_match,
                    'input': test_input if not is_hidden else '[Hidden]',
                    'expected': expected_output if not is_hidden else '[Hidden]',
                    'actual': actual_output if not is_hidden else '[Hidden]',
                    'marks': test_marks if is_match else 0,
                    'max_marks': test_marks
                })

            except Exception as e:
                logger.error(f"Test case {idx + 1} execution error: {str(e)}")
                test_results.append({
                    'test_case': idx + 1,
                    'passed': False,
                    'error': str(e),
                    'marks': 0,
                    'max_marks': test_marks
                })

        # Calculate final result
        is_correct = passed_count == len(test_cases)
        
        # Proportional marking based on passed test cases
        marks_obtained = min(total_marks_scored, max_marks)

        return {
            'grading_type': 'auto',
            'is_correct': is_correct,
            'marks_obtained': round(marks_obtained, 2),
            'max_marks': max_marks,
            'auto_graded': True,
            'status': 'graded',
            'execution_output': original_output,  # Include the output from user's print statements
            'execution_time_ms': total_execution_time,
            'test_cases_passed': passed_count,
            'test_cases_total': len(test_cases),
            'grading_details': {
                'test_results': test_results,
                'pass_rate': f"{passed_count}/{len(test_cases)}"
            }
        }

    def _wrap_code_for_testing(self, code: str, test_input: str, language: str) -> str:
        """
        Wrap user code to execute with test input and capture output.
        Removes manual testing blocks and adds test case execution.
        """
        if language == 'python':
            # Remove the if __name__ == "__main__": block if present
            import re
            # Remove the entire if __name__ == "__main__": block
            code_cleaned = re.sub(
                r'\n*if\s+__name__\s*==\s*["\']__main__["\']\s*:.*$',
                '',
                code,
                flags=re.DOTALL | re.MULTILINE
            ).strip()
            
            # Extract function name (assumes single function definition)
            func_match = re.search(r'def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(', code_cleaned)
            if not func_match:
                # No function found, just run the code as-is
                return code
            
            func_name = func_match.group(1)
            
            # Wrap to call the function with test input
            wrapped = f"""{code_cleaned}

# Test execution
if __name__ == "__main__":
    result = {func_name}({test_input})
    print(result)
"""
            return wrapped
            
        elif language == 'javascript':
            import re
            # Strip every console.log call and comment-only lines —
            # these are the manual test invocations at the bottom of the
            # candidate's code and would pollute the grader's output capture.
            lines = code.split('\n')
            cleaned_lines = [
                line for line in lines
                if not re.match(r'^\s*console\.log\s*\(', line)
                and not re.match(r'^\s*//', line)
            ]
            code_cleaned = '\n'.join(cleaned_lines).strip()

            # Extract function name
            func_match = re.search(r'function\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(', code_cleaned)
            if not func_match:
                # Try arrow function or const function
                func_match = re.search(r'(?:const|let|var)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*=', code_cleaned)
            
            if not func_match:
                # No function found, just run the code as-is
                return code
            
            func_name = func_match.group(1)
            
            # Wrap to call the function with test input
            wrapped = f"""{code_cleaned}

// Test execution
console.log({func_name}({test_input}));
"""
            return wrapped
        
        # Default: return code as-is
        return code

    def _compare_outputs(self, actual: str, expected: str) -> bool:
        """Compare actual output with expected output (flexible comparison)"""
        # Remove trailing whitespace and normalize
        actual_normalized = actual.strip().lower()
        expected_normalized = expected.strip().lower()

        # Exact match first
        if actual_normalized == expected_normalized:
            return True

        # Whitespace-stripped comparison (handles JS array/object formatting
        # differences, e.g. "[ 1, 2, 3 ]" vs "[1,2,3]")
        if actual_normalized.replace(' ', '') == expected_normalized.replace(' ', ''):
            return True

        # Try parsing as numbers for numeric comparison
        try:
            actual_num = float(actual_normalized)
            expected_num = float(expected_normalized)
            return abs(actual_num - expected_num) < 1e-6
        except ValueError:
            pass

        # Line-by-line comparison (ignore extra whitespace)
        actual_lines = [line.strip() for line in actual_normalized.split('\n') if line.strip()]
        expected_lines = [line.strip() for line in expected_normalized.split('\n') if line.strip()]

        return actual_lines == expected_lines

    def _compare_sql_results(self, actual: Any, expected: Any) -> bool:
        """Compare SQL query results - flexible comparison that handles different orderings"""
        if actual == expected:
            return True

        try:
            # Extract JSON from actual output (it contains both table and JSON)
            actual_json = None
            if isinstance(actual, str):
                # Look for "--- JSON Output ---" marker and extract JSON part
                if "--- JSON Output ---" in actual:
                    json_part = actual.split("--- JSON Output ---")[1].strip()
                    actual_json = json.loads(json_part)
                else:
                    # Try parsing the whole string
                    actual_json = json.loads(actual)
            else:
                actual_json = actual
            
            # Parse expected (stored in database)
            expected_json = None
            if isinstance(expected, str):
                expected_json = json.loads(expected)
            elif isinstance(expected, list):
                expected_json = expected
            else:
                expected_json = expected
            
            # Both should be lists of dicts (SQL rows)
            if not isinstance(actual_json, list) or not isinstance(expected_json, list):
                return False
            
            # If lengths don't match, results are different
            if len(actual_json) != len(expected_json):
                return False
            
            # Sort both lists by converting dicts to sorted tuples for comparison
            # This handles different row orders
            def normalize_row(row):
                """Convert row dict to comparable tuple"""
                if isinstance(row, dict):
                    # Sort keys and convert values to strings for comparison
                    return tuple(sorted((k, str(v).lower()) for k, v in row.items()))
                return row
            
            actual_normalized = sorted([normalize_row(row) for row in actual_json])
            expected_normalized = sorted([normalize_row(row) for row in expected_json])
            
            return actual_normalized == expected_normalized
            
        except (json.JSONDecodeError, TypeError, AttributeError) as e:
            logger.warning(f"SQL result comparison failed with error: {e}")
            # Fallback to string comparison
            if isinstance(actual, str) and isinstance(expected, str):
                return actual.strip().lower() == expected.strip().lower()
            return False

    # ============================================
    # Descriptive Question Handling
    # ============================================

    def _grade_descriptive_pending(self) -> Dict[str, Any]:
        """Mark descriptive question as pending manual grading"""
        return {
            'grading_type': 'manual',
            'is_correct': None,
            'marks_obtained': 0,
            'auto_graded': False,
            'manually_graded': False,
            'status': 'pending',
            'grading_details': {
                'message': 'This answer requires manual grading by an admin'
            }
        }

    async def grade_descriptive_manually(
        self,
        submission_id: str,
        marks_obtained: float,
        grader_id: str,
        feedback: Optional[str] = None,
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """Manually grade a descriptive answer"""
        grading_result = {
            'grading_type': 'manual',
            'marks_obtained': marks_obtained,
            'manually_graded': True,
            'graded_by': grader_id,
            'graded_at': datetime.utcnow().isoformat(),
            'grader_feedback': feedback,
            'grading_notes': notes,
            'status': 'graded'
        }

        # Log the manual grading
        await self._log_grading(submission_id, grading_result)

        return grading_result

    # ============================================
    # Grading Logs
    # ============================================

    async def _log_grading(
        self,
        submission_id: str,
        grading_result: Dict[str, Any]
    ) -> None:
        """Log grading action to grading_logs table"""
        try:
            # Get submission details (use service client)
            submission_response = self.service_supabase.table('submissions') \
                .select('session_id, question_id, marks_obtained') \
                .eq('id', submission_id) \
                .single() \
                .execute()

            if not submission_response.data:
                logger.error(f"Submission {submission_id} not found for logging")
                return

            submission = submission_response.data

            log_data = {
                'submission_id': submission_id,
                'session_id': submission['session_id'],
                'question_id': submission['question_id'],
                'grading_type': grading_result.get('grading_type', 'auto'),
                'marks_before': submission.get('marks_obtained', 0),
                'marks_after': grading_result.get('marks_obtained', 0),
                'graded_by': grading_result.get('graded_by'),
                'grading_details': grading_result.get('grading_details', {}),
                'comments': grading_result.get('grader_feedback')
            }

            self.service_supabase.table('grading_logs').insert(log_data).execute()

        except Exception as e:
            logger.error(f"Failed to log grading for submission {submission_id}: {str(e)}")

    # ============================================
    # Session Score Calculation
    # ============================================

    async def calculate_session_score(self, session_id: str) -> Dict[str, Any]:
        """Calculate total score for a test session"""
        try:
            # Get all submissions for this session (use service client)
            submissions_response = self.service_supabase.table('submissions') \
                .select('marks_obtained, max_marks, status') \
                .eq('session_id', session_id) \
                .execute()

            submissions = submissions_response.data or []

            total_marks_obtained = sum(
                float(sub.get('marks_obtained', 0))
                for sub in submissions
                if sub.get('status') == 'graded'
            )

            # Use the test's fixed total_marks (not the sum of only attempted questions)
            session_response = self.service_supabase.table('test_sessions') \
                .select('test_id') \
                .eq('id', session_id) \
                .single() \
                .execute()
            test_id = session_response.data.get('test_id') if session_response.data else None

            total_marks = 0
            if test_id:
                test_response = self.service_supabase.table('tests') \
                    .select('total_marks') \
                    .eq('id', test_id) \
                    .single() \
                    .execute()
                total_marks = int(test_response.data.get('total_marks', 0)) if test_response.data else 0

            # Fall back to summing attempted questions if test lookup fails
            if total_marks == 0:
                total_marks = sum(int(sub.get('max_marks', 0)) for sub in submissions)

            percentage = (total_marks_obtained / total_marks * 100) if total_marks > 0 else 0

            # Update session with scoring (use service client)
            self.service_supabase.table('test_sessions') \
                .update({
                    'total_marks_obtained': round(total_marks_obtained, 2),
                    'total_marks': total_marks,
                    'percentage_score': round(percentage, 2)
                }) \
                .eq('id', session_id) \
                .execute()

            return {
                'total_marks_obtained': round(total_marks_obtained, 2),
                'total_marks': total_marks,
                'percentage_score': round(percentage, 2),
                'graded_count': len([s for s in submissions if s.get('status') == 'graded']),
                'total_questions': len(submissions)
            }

        except Exception as e:
            logger.error(f"Failed to calculate session score for {session_id}: {str(e)}")
            raise
