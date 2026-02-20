"""
Code execution service with fallback to local execution.
Supports Python, JavaScript, and SQL execution.
SQL queries automatically translate MySQL/PostgreSQL syntax to SQLite.
Note: Uses base64 encoding for SQL string safety
"""
import httpx
import logging
import subprocess
import tempfile
import os
import json
import base64
from typing import Dict, List, Optional, Any
from pathlib import Path
from app.core.config import settings

logger = logging.getLogger(__name__)


class CodeExecutionService:
    """Service for executing code using Piston API."""
    
    # Language mappings for Piston API
    LANGUAGE_MAP = {
        'javascript': {'language': 'javascript', 'version': '18.15.0'},
        'python': {'language': 'python', 'version': '3.10.0'},
        'java': {'language': 'java', 'version': '15.0.2'},
        'cpp': {'language': 'c++', 'version': '10.2.0'},
        'c': {'language': 'c', 'version': '10.2.0'},
        'csharp': {'language': 'csharp', 'version': '6.12.0'},
        'go': {'language': 'go', 'version': '1.16.2'},
        'rust': {'language': 'rust', 'version': '1.68.2'},
        'ruby': {'language': 'ruby', 'version': '3.0.1'},
        'php': {'language': 'php', 'version': '8.2.3'},
        'typescript': {'language': 'typescript', 'version': '5.0.3'},
        'swift': {'language': 'swift', 'version': '5.3.3'},
        'kotlin': {'language': 'kotlin', 'version': '1.8.20'},
        'scala': {'language': 'scala', 'version': '3.2.2'},
        'r': {'language': 'r', 'version': '4.1.1'},
        'perl': {'language': 'perl', 'version': '5.36.0'},
        'haskell': {'language': 'haskell', 'version': '9.0.1'},
        'lua': {'language': 'lua', 'version': '5.4.4'},
        'elixir': {'language': 'elixir', 'version': '1.11.3'},
        'clojure': {'language': 'clojure', 'version': '1.10.3'},
        'bash': {'language': 'bash', 'version': '5.2.0'},
        'sql': {'language': 'sqlite3', 'version': '3.36.0'},
    }
    
    def __init__(self):
        """Initialize the code execution service."""
        self.base_url = settings.PISTON_API_URL
        self.client = httpx.AsyncClient(timeout=30.0)
    
    def translate_sql_syntax(self, query: str) -> str:
        """
        Automatically translate MySQL/PostgreSQL syntax to SQLite.
        Allows users to write queries in familiar syntax.
        
        Args:
            query: SQL query possibly containing MySQL/PostgreSQL syntax
            
        Returns:
            Translated query compatible with SQLite
        """
        import re
        
        # Track if translation occurred (for logging)
        original_query = query
        
        # 1. Replace NOW() with datetime('now')
        query = re.sub(r'\bNOW\s*\(\s*\)', "datetime('now')", query, flags=re.IGNORECASE)
        
        # 2. Replace CURDATE() and CURRENT_DATE with date('now')
        query = re.sub(r'\bCURDATE\s*\(\s*\)', "date('now')", query, flags=re.IGNORECASE)
        query = re.sub(r'\bCURRENT_DATE\b', "date('now')", query, flags=re.IGNORECASE)
        
        # 3. Replace CURRENT_TIME with time('now')
        query = re.sub(r'\bCURRENT_TIME\b', "time('now')", query, flags=re.IGNORECASE)
        
        # 4. Replace CURRENT_TIMESTAMP with datetime('now')
        query = re.sub(r'\bCURRENT_TIMESTAMP\b', "datetime('now')", query, flags=re.IGNORECASE)
        
        # 5. Handle INTERVAL expressions
        # Pattern: INTERVAL N DAY/MONTH/YEAR/HOUR/MINUTE/SECOND
        # Examples: 
        #   NOW() - INTERVAL 30 DAY -> datetime('now', '-30 days')
        #   date + INTERVAL 1 MONTH -> datetime(date, '+1 months')
        
        # Handle subtraction: ... - INTERVAL N UNIT
        def replace_interval_subtract(match):
            base_expr = match.group(1).strip()
            num = match.group(2)
            unit = match.group(3).lower()
            
            # Map MySQL units to SQLite modifiers (SQLite uses singular forms)
            unit_map = {
                'day': 'day', 'days': 'day',
                'month': 'month', 'months': 'month',
                'year': 'year', 'years': 'year',
                'hour': 'hour', 'hours': 'hour',
                'minute': 'minute', 'minutes': 'minute',
                'second': 'second', 'seconds': 'second'
            }
            sqlite_unit = unit_map.get(unit, unit)
            
            # If base expression is already datetime('now'), simplify
            if "datetime('now')" in base_expr or "date('now')" in base_expr:
                return f"{base_expr.replace(')', '')}, '-{num} {sqlite_unit}')"
            else:
                return f"datetime({base_expr}, '-{num} {sqlite_unit}')"
        
        query = re.sub(
            r'(\b\w+\([^)]*\)|[\w.]+)\s*-\s*INTERVAL\s+(\d+)\s+(\w+)',
            replace_interval_subtract,
            query,
            flags=re.IGNORECASE
        )
        
        # Handle addition: ... + INTERVAL N UNIT
        def replace_interval_add(match):
            base_expr = match.group(1).strip()
            num = match.group(2)
            unit = match.group(3).lower()
            
            unit_map = {
                'day': 'day', 'days': 'day',
                'month': 'month', 'months': 'month',
                'year': 'year', 'years': 'year',
                'hour': 'hour', 'hours': 'hour',
                'minute': 'minute', 'minutes': 'minute',
                'second': 'second', 'seconds': 'second'
            }
            sqlite_unit = unit_map.get(unit, unit)
            
            if "datetime('now')" in base_expr or "date('now')" in base_expr:
                return f"{base_expr.replace(')', '')}, '+{num} {sqlite_unit}')"
            else:
                return f"datetime({base_expr}, '+{num} {sqlite_unit}')"
        
        query = re.sub(
            r'(\b\w+\([^)]*\)|[\w.]+)\s*\+\s*INTERVAL\s+(\d+)\s+(\w+)',
            replace_interval_add,
            query,
            flags=re.IGNORECASE
        )
        
        # 6. Replace DATE_ADD(date, INTERVAL N UNIT)
        def replace_date_add(match):
            date_expr = match.group(1).strip()
            num = match.group(2)
            unit = match.group(3).lower()
            
            unit_map = {
                'day': 'day', 'days': 'day',
                'month': 'month', 'months': 'month',
                'year': 'year', 'years': 'year',
                'hour': 'hour', 'hours': 'hour',
                'minute': 'minute', 'minutes': 'minute',
                'second': 'second', 'seconds': 'second'
            }
            sqlite_unit = unit_map.get(unit, unit)
            return f"datetime({date_expr}, '+{num} {sqlite_unit}')"
        
        query = re.sub(
            r'\bDATE_ADD\s*\(\s*([^,]+),\s*INTERVAL\s+(\d+)\s+(\w+)\s*\)',
            replace_date_add,
            query,
            flags=re.IGNORECASE
        )
        
        # 7. Replace DATE_SUB(date, INTERVAL N UNIT)
        def replace_date_sub(match):
            date_expr = match.group(1).strip()
            num = match.group(2)
            unit = match.group(3).lower()
            
            unit_map = {
                'day': 'day', 'days': 'day',
                'month': 'month', 'months': 'month',
                'year': 'year', 'years': 'year',
                'hour': 'hour', 'hours': 'hour',
                'minute': 'minute', 'minutes': 'minute',
                'second': 'second', 'seconds': 'second'
            }
            sqlite_unit = unit_map.get(unit, unit)
            return f"datetime({date_expr}, '-{num} {sqlite_unit}')"
        
        query = re.sub(
            r'\bDATE_SUB\s*\(\s*([^,]+),\s*INTERVAL\s+(\d+)\s+(\w+)\s*\)',
            replace_date_sub,
            query,
            flags=re.IGNORECASE
        )
        
        # 8. Replace date extraction functions
        query = re.sub(r'\bYEAR\s*\(\s*([^)]+)\s*\)', r"strftime('%Y', \1)", query, flags=re.IGNORECASE)
        query = re.sub(r'\bMONTH\s*\(\s*([^)]+)\s*\)', r"strftime('%m', \1)", query, flags=re.IGNORECASE)
        query = re.sub(r'\bDAY\s*\(\s*([^)]+)\s*\)', r"strftime('%d', \1)", query, flags=re.IGNORECASE)
        query = re.sub(r'\bHOUR\s*\(\s*([^)]+)\s*\)', r"strftime('%H', \1)", query, flags=re.IGNORECASE)
        query = re.sub(r'\bMINUTE\s*\(\s*([^)]+)\s*\)', r"strftime('%M', \1)", query, flags=re.IGNORECASE)
        query = re.sub(r'\bSECOND\s*\(\s*([^)]+)\s*\)', r"strftime('%S', \1)", query, flags=re.IGNORECASE)
        
        # 9. Replace IFNULL with COALESCE (SQLite supports COALESCE better)
        query = re.sub(r'\bIFNULL\s*\(', 'COALESCE(', query, flags=re.IGNORECASE)
        
        # 10. Replace CONCAT with || operator
        # CONCAT(a, b, c) -> a || b || c
        def replace_concat(match):
            args = match.group(1)
            # Split by commas not inside parentheses
            parts = []
            depth = 0
            current = []
            for char in args:
                if char == '(':
                    depth += 1
                    current.append(char)
                elif char == ')':
                    depth -= 1
                    current.append(char)
                elif char == ',' and depth == 0:
                    parts.append(''.join(current).strip())
                    current = []
                else:
                    current.append(char)
            if current:
                parts.append(''.join(current).strip())
            
            return ' || '.join(parts)
        
        query = re.sub(r'\bCONCAT\s*\(([^)]+)\)', replace_concat, query, flags=re.IGNORECASE)
        
        # Log translation if changes were made
        if query != original_query:
            logger.info(f"SQL syntax translated for SQLite compatibility")
            logger.debug(f"Original: {original_query[:200]}")
            logger.debug(f"Translated: {query[:200]}")
        
        return query
    
    async def get_supported_languages(self) -> List[Dict[str, Any]]:
        """
        Get list of supported programming languages from Piston API.
        
        Returns:
            List of supported languages with their versions
        """
        try:
            response = await self.client.get(f"{self.base_url}/runtimes")
            
            if response.status_code == 200:
                runtimes = response.json()
                return [
                    {
                        'language': runtime['language'],
                        'version': runtime['version'],
                        'aliases': runtime.get('aliases', [])
                    }
                    for runtime in runtimes
                ]
            else:
                logger.error(f"Failed to fetch languages. Status: {response.status_code}")
                return []
                
        except Exception as e:
            logger.error(f"Error fetching supported languages: {str(e)}")
            return []
    
    async def execute_code(
        self,
        code: str,
        language: str,
        stdin: Optional[str] = None,
        args: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Execute code using Piston API.
        
        Args:
            code: The source code to execute
            language: Programming language (e.g., 'python', 'javascript')
            stdin: Optional standard input for the program
            args: Optional command-line arguments
            
        Returns:
            Dictionary containing execution results:
            {
                'success': bool,
                'output': str,
                'error': str,
                'stdout': str,
                'stderr': str,
                'runtime': str,
                'language': str,
                'version': str
            }
        """
        try:
            # Get language info from mapping
            lang_info = self.LANGUAGE_MAP.get(language.lower())
            
            if not lang_info:
                return {
                    'success': False,
                    'error': f"Unsupported language: {language}. Please choose from: {', '.join(self.LANGUAGE_MAP.keys())}",
                    'output': '',
                    'stdout': '',
                    'stderr': '',
                    'runtime': 0,
                    'language': language,
                    'version': 'unknown'
                }
            
            # Prepare request payload
            payload = {
                'language': lang_info['language'],
                'version': lang_info['version'],
                'files': [
                    {
                        'name': f"main.{self._get_file_extension(language)}",
                        'content': code
                    }
                ],
                'stdin': stdin or '',
                'args': args or [],
                'compile_timeout': 10000,  # 10 seconds
                'run_timeout': 3000,  # 3 seconds
                'compile_memory_limit': -1,
                'run_memory_limit': -1
            }
            
            logger.info(f"Executing {language} code via Piston API")
            
            # Execute code
            response = await self.client.post(
                f"{self.base_url}/execute",
                json=payload
            )
            
            if response.status_code == 200:
                result = response.json()
                
                # Process compilation result
                compile_output = result.get('compile', {})
                compile_stdout = compile_output.get('stdout', '')
                compile_stderr = compile_output.get('stderr', '')
                
                # Process run result
                run_output = result.get('run', {})
                run_stdout = run_output.get('stdout', '')
                run_stderr = run_output.get('stderr', '')
                
                # Combine outputs
                stdout = (compile_stdout + run_stdout).strip()
                stderr = (compile_stderr + run_stderr).strip()
                
                # Determine success
                success = run_output.get('code', 1) == 0 and not stderr
                
                return {
                    'success': success,
                    'output': stdout if stdout else stderr,
                    'error': stderr if stderr else '',
                    'stdout': stdout,
                    'stderr': stderr,
                    'runtime': run_output.get('runtime', 0),
                    'language': lang_info['language'],
                    'version': lang_info['version'],
                    'exit_code': run_output.get('code', 0)
                }
            else:
                # Get detailed error message from response
                try:
                    error_body = response.json()
                    error_detail = error_body.get('message', str(error_body))
                except:
                    error_detail = response.text or "No error details available"
                
                # If Piston API is unavailable (401 whitelist), fallback to local execution
                if response.status_code == 401 and language.lower() in ['python', 'javascript']:
                    logger.warning(f"Piston API unavailable (401), falling back to local execution for {language}")
                    return await self.execute_code_local(code, language, stdin)
                
                error_msg = f"Piston API Error (Status {response.status_code}): {error_detail}"
                logger.error(f"{error_msg}\nPayload: {payload}")
                
                return {
                    'success': False,
                    'error': error_msg,
                    'output': '',
                    'stdout': '',
                    'stderr': error_msg,
                    'runtime': 0,
                    'language': language,
                    'version': 'unknown'
                }
                
        except httpx.TimeoutException:
            error_msg = "Code execution timed out (maximum 30 seconds)"
            logger.error(error_msg)
            
            return {
                'success': False,
                'error': error_msg,
                'output': error_msg,
                'stdout': '',
                'stderr': error_msg,
                'runtime': 0,
                'language': language,
                'version': 'unknown'
            }
            
        except Exception as e:
            error_msg = f"Error executing code: {str(e)}"
            logger.error(error_msg)
            
            return {
                'success': False,
                'error': error_msg,
                'output': error_msg,
                'stdout': '',
                'stderr': error_msg,
                'runtime': 0,
                'language': language,
                'version': 'unknown'
            }
    
    async def execute_code_local(
        self,
        code: str,
        language: str,
        stdin: Optional[str] = None,
        timeout_seconds: int = 10
    ) -> Dict[str, Any]:
        """
        Execute code locally as fallback when Piston API is unavailable.
        Supports Python, JavaScript (Node.js), and SQL (SQLite).
        """
        try:
            import time
            start_time = time.time()
            
            # Prepare command based on language
            if language.lower() == 'python':
                cmd = ['python', '-c', code]
            elif language.lower() == 'javascript':
                cmd = ['node', '-e', code]
            elif language.lower() == 'sql':
                # SQL handled specially - shouldn't reach here
                return {
                    'success': False,
                    'error': 'SQL should use execute_sql_with_schema method',
                    'output': '',
                    'stdout': '',
                    'stderr': 'SQL should use execute_sql_with_schema method',
                    'runtime': 0,
                    'language': language,
                    'version': 'local'
                }
            else:
                return {
                    'success': False,
                    'error': f'Local execution not supported for {language}',
                    'output': '',
                    'stdout': '',
                    'stderr': f'Language {language} not supported for local execution',
                    'runtime': 0,
                    'language': language,
                    'version': 'local'
                }
            
            # Execute with timeout
            process = subprocess.run(
                cmd,
                input=stdin,
                capture_output=True,
                text=True,
                timeout=timeout_seconds
            )
            
            runtime = int((time.time() - start_time) * 1000)  # milliseconds
            stdout = process.stdout
            stderr = process.stderr
            exit_code = process.returncode
            
            success = exit_code == 0 and not stderr
            
            logger.info(f"[CODE_EXEC] Language: {language}, Exit: {exit_code}, Stdout length: {len(stdout) if stdout else 0}, Stderr: {stderr[:100] if stderr else 'None'}")
            
            return {
                'success': success,
                'output': stdout if stdout else stderr,
                'error': stderr if stderr else '',
                'stdout': stdout,
                'stderr': stderr,
                'runtime': runtime,
                'language': language,
                'version': 'local',
                'exit_code': exit_code
            }
            
        except subprocess.TimeoutExpired:
            return {
                'success': False,
                'error': f'Execution timed out after {timeout_seconds} seconds',
                'output': '',
                'stdout': '',
                'stderr': f'Timeout after {timeout_seconds}s',
                'runtime': timeout_seconds * 1000,
                'language': language,
                'version': 'local'
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'output': '',
                'stdout': '',
                'stderr': str(e),
                'runtime': 0,
                'language': language,
                'version': 'local'
            }
    
    def _get_file_extension(self, language: str) -> str:
        """Get file extension for a given language."""
        extensions = {
            'javascript': 'js',
            'python': 'py',
            'java': 'java',
            'cpp': 'cpp',
            'c': 'c',
            'csharp': 'cs',
            'go': 'go',
            'rust': 'rs',
            'ruby': 'rb',
            'php': 'php',
            'typescript': 'ts',
            'swift': 'swift',
            'kotlin': 'kt',
            'scala': 'scala',
            'r': 'r',
            'perl': 'pl',
            'haskell': 'hs',
            'lua': 'lua',
            'elixir': 'ex',
            'clojure': 'clj',
            'bash': 'sh',
            'sql': 'sql',
        }
        return extensions.get(language.lower(), 'txt')
    
    async def execute_sql_with_schema(
        self,
        schema: str,
        seed_data: str,
        query: str
    ) -> Dict[str, Any]:
        """
        Execute SQL query with provided schema and seed data.
        Creates tables, inserts data, then runs the query.
        Automatically translates MySQL/PostgreSQL syntax to SQLite.
        
        Args:
            schema: CREATE TABLE statements
            seed_data: INSERT statements
            query: The SQL query to execute (MySQL/PostgreSQL syntax supported)
            
        Returns:
            Dictionary with execution results including formatted output
        """
        try:
            import base64
            
            # Translate MySQL/PostgreSQL syntax to SQLite
            query = self.translate_sql_syntax(query)
            
            # Use base64 encoding to safely pass SQL strings (no escaping issues)
            schema_b64 = base64.b64encode(schema.encode('utf-8')).decode('ascii')
            seed_b64 = base64.b64encode(seed_data.encode('utf-8')).decode('ascii')
            query_b64 = base64.b64encode(query.encode('utf-8')).decode('ascii')
            
            # Create a Python script that executes SQL and formats output nicely
            python_wrapper = f'''
import sqlite3
import json
import base64

# Connect to in-memory database
conn = sqlite3.connect(':memory:')
conn.row_factory = sqlite3.Row  # Enable column access by name
cursor = conn.cursor()

try:
    # Decode SQL from base64 (safe string handling)
    schema = base64.b64decode("{schema_b64}").decode('utf-8')
    seed_data = base64.b64decode("{seed_b64}").decode('utf-8')
    query = base64.b64decode("{query_b64}").decode('utf-8')
    
    # Execute schema
    cursor.executescript(schema)
    
    # Execute seed data
    if seed_data.strip():
        cursor.executescript(seed_data)
    
    # Execute user query
    cursor.execute(query)
    
    # Fetch results
    rows = cursor.fetchall()
    
    # Format output
    if rows:
        # Get column names
        columns = [description[0] for description in cursor.description]
        
        # Convert rows to list of dicts
        result_list = []
        for row in rows:
            result_list.append(dict(zip(columns, row)))
        
        # Print as formatted table
        print(f"Returned {{len(result_list)}} row(s)\\n")
        
        # Print column headers
        col_widths = {{col: max(len(col), 10) for col in columns}}
        for col in columns:
            for row in rows:
                val_len = len(str(dict(zip(columns, row))[col]))
                if val_len > col_widths[col]:
                    col_widths[col] = val_len
        
        header = " | ".join(col.ljust(col_widths[col]) for col in columns)
        print(header)
        print("-" * len(header))
        
        # Print rows
        for row in rows:
            row_dict = dict(zip(columns, row))
            print(" | ".join(str(row_dict[col]).ljust(col_widths[col]) for col in columns))
        
        # Also print JSON for programmatic access
        print("\\n--- JSON Output ---")
        print(json.dumps(result_list, indent=2, default=str))
    else:
        print("Query executed successfully. No rows returned.")
        print("\\n--- JSON Output ---")
        print("[]")
    
    conn.commit()

except Exception as e:
    error_msg = str(e)
    print(f"SQL Error: {{error_msg}}")
    print("\\nNote: This system uses SQLite. Queries are automatically translated from MySQL/PostgreSQL syntax.")
    print("If you encounter errors, ensure your query uses standard SQL syntax.")
    import traceback
    traceback.print_exc()
finally:
    conn.close()
            '''.strip()
            
            # Execute using local Python (more reliable than Piston API)
            result = await self.execute_code_local(
                code=python_wrapper,
                language='python',
                stdin=None,
                timeout_seconds=10
            )
            
            return result
            
        except Exception as e:
            logger.error(f"SQL execution with schema failed: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'output': '',
                'stdout': '',
                'stderr': str(e),
                'runtime': 0,
                'language': 'sql',
                'version': 'unknown'
            }
    
    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()


# Singleton instance
code_execution_service = CodeExecutionService()
