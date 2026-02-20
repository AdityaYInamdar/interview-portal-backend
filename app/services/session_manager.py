"""
Session Manager Service
Handles strict session control, one-time access enforcement,
session lifecycle, and security validation
"""
import secrets
import hashlib
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import logging
from app.core.supabase import get_supabase_client, SupabaseClient

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages test sessions with strict control and security"""

    def __init__(self):
        self.supabase = get_supabase_client()  # Regular client (respects RLS)
        self.service_supabase = SupabaseClient.get_service_client()  # Service client (bypasses RLS)

    # ============================================
    # Token Generation
    # ============================================

    def generate_invitation_token(self, test_id: str, email: str) -> str:
        """Generate unique invitation token"""
        random_part = secrets.token_urlsafe(32)
        unique_string = f"{test_id}:{email}:{random_part}:{datetime.utcnow().isoformat()}"
        token_hash = hashlib.sha256(unique_string.encode()).hexdigest()
        return f"invite_{token_hash[:48]}"

    def generate_session_token(self, invitation_id: str, candidate_email: str) -> str:
        """Generate unique session token"""
        random_part = secrets.token_urlsafe(32)
        unique_string = f"{invitation_id}:{candidate_email}:{random_part}:{datetime.utcnow().isoformat()}"
        token_hash = hashlib.sha256(unique_string.encode()).hexdigest()
        return f"session_{token_hash[:48]}"

    # ============================================
    # Invitation Creation
    # ============================================

    async def create_invitation(
        self,
        test_id: str,
        candidate_email: str,
        candidate_name: str,
        expires_in_hours: int,
        created_by: str,
        company_id: str
    ) -> Dict[str, Any]:
        """
        Create a test invitation with unique token
        
        Returns:
            Invitation data with token and URL
        """
        try:
            # Generate unique token
            invitation_token = self.generate_invitation_token(test_id, candidate_email)
            
            # Calculate expiry
            expires_at = datetime.utcnow() + timedelta(hours=expires_in_hours)
            
            # Create invitation
            invitation_data = {
                'test_id': test_id,
                'candidate_email': candidate_email.lower().strip(),
                'candidate_name': candidate_name.strip(),
                'invitation_token': invitation_token,
                'expires_at': expires_at.isoformat(),
                'is_used': False,
                'created_by': created_by,
                'company_id': company_id
            }
            
            response = self.supabase.table('test_invitations') \
                .insert(invitation_data) \
                .execute()
            
            if not response.data:
                raise Exception("Failed to create invitation")
            
            invitation = response.data[0]
            
            # Generate invitation URL (will be configured based on frontend URL)
            invitation_url = f"/test/start?token={invitation_token}"
            
            return {
                **invitation,
                'invitation_url': invitation_url
            }
            
        except Exception as e:
            logger.error(f"Failed to create invitation: {str(e)}")
            raise

    async def create_bulk_invitations(
        self,
        test_id: str,
        candidates: list,
        expires_in_hours: int,
        created_by: str,
        company_id: str
    ) -> Dict[str, Any]:
        """
        Create multiple invitations at once
        
        Args:
            candidates: List of dicts with 'email' and 'name'
        
        Returns:
            Summary of created invitations
        """
        try:
            invitations = []
            errors = []
            
            for candidate in candidates:
                try:
                    invitation = await self.create_invitation(
                        test_id=test_id,
                        candidate_email=candidate['email'],
                        candidate_name=candidate['name'],
                        expires_in_hours=expires_in_hours,
                        created_by=created_by,
                        company_id=company_id
                    )
                    invitations.append(invitation)
                except Exception as e:
                    errors.append({
                        'email': candidate.get('email'),
                        'error': str(e)
                    })
            
            return {
                'total': len(candidates),
                'successful': len(invitations),
                'failed': len(errors),
                'invitations': invitations,
                'errors': errors
            }
            
        except Exception as e:
            logger.error(f"Bulk invitation creation failed: {str(e)}")
            raise

    # ============================================
    # Session Creation & Validation
    # ============================================

    async def validate_invitation(self, invitation_token: str) -> Dict[str, Any]:
        """
        Validate invitation token before starting session
        
        Checks:
        - Token exists
        - Not expired
        - Not already used
        
        Returns:
            Invitation data if valid
        
        Note: Uses service client to bypass RLS (public endpoint)
        """
        try:
            # Get invitation (use service client to bypass RLS for public access)
            response = self.service_supabase.table('test_invitations') \
                .select('*, test:tests(*)') \
                .eq('invitation_token', invitation_token) \
                .single() \
                .execute()
            
            if not response.data:
                return {
                    'valid': False,
                    'error': 'Invalid invitation token'
                }
            
            invitation = response.data
            
            # Check if already used
            if invitation.get('is_used'):
                # Find the existing session for this invitation.
                # If it is still active (not completed, not terminated) the
                # candidate reloaded the page and should be allowed to resume.
                existing = self.service_supabase.table('test_sessions') \
                    .select('*') \
                    .eq('invitation_id', invitation['id']) \
                    .neq('status', 'terminated') \
                    .execute()

                active = [s for s in (existing.data or []) if not s.get('is_completed')]
                if active:
                    return {
                        'valid': True,
                        'is_resuming': True,
                        'invitation': invitation,
                        'test': invitation.get('test'),
                        'session': active[0],
                    }

                return {
                    'valid': False,
                    'error': 'This invitation has already been used. Please contact the administrator.'
                }
            
            # Check expiry
            expires_at = datetime.fromisoformat(invitation['expires_at'].replace('Z', '+00:00'))
            if datetime.utcnow().replace(tzinfo=expires_at.tzinfo) > expires_at:
                return {
                    'valid': False,
                    'error': 'This invitation has expired.'
                }

            # Check if the test has been published
            test_data = invitation.get('test') or {}
            if not test_data.get('is_published'):
                return {
                    'valid': False,
                    'error': 'This test has not been published yet. Please contact the administrator.'
                }

            return {
                'valid': True,
                'invitation': invitation,
                'test': invitation.get('test')
            }
            
        except Exception as e:
            logger.error(f"Invitation validation failed: {str(e)}")
            return {
                'valid': False,
                'error': 'Failed to validate invitation'
            }

    async def start_session(
        self,
        invitation_token: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        browser_info: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Start a test session (one-time only)
        
        This enforces strict session control:
        - Marks invitation as used
        - Creates new session
        - Generates session token
        - Sets expiry based on test duration
        
        Returns:
            Session data with token
        """
        try:
            # Validate invitation first
            validation = await self.validate_invitation(invitation_token)
            
            if not validation.get('valid'):
                return {
                    'success': False,
                    'error': validation.get('error')
                }
            
            invitation = validation['invitation']

            # If validate_invitation detected an already-used invitation with an
            # active session (page reload / browser restart scenario), return that
            # session directly so the candidate can continue their test.
            if validation.get('is_resuming') and validation.get('session'):
                return {
                    'success': True,
                    'session': validation['session'],
                    'resumed': True
                }

            # Check if session already exists for this invitation (use service client)
            # Exclude terminated sessions (those are reset sessions)
            existing_session = self.service_supabase.table('test_sessions') \
                .select('*') \
                .eq('invitation_id', invitation['id']) \
                .neq('status', 'terminated') \
                .execute()
            
            if existing_session.data and len(existing_session.data) > 0:
                session = existing_session.data[0]

                # Resume any active (non-completed) session — handles page reloads
                if not session.get('is_completed'):
                    return {
                        'success': True,
                        'session': session,
                        'resumed': True
                    }

                # Session was genuinely completed
                return {
                    'success': False,
                    'error': 'This test has already been completed. Contact administrator to reset.'
                }
            
            # Get test details for duration (use service client)
            test_response = self.service_supabase.table('tests') \
                .select('duration_minutes, total_marks') \
                .eq('id', invitation['test_id']) \
                .single() \
                .execute()
            
            if not test_response.data:
                return {
                    'success': False,
                    'error': 'Test not found'
                }
            
            test = test_response.data
            
            # Generate session token
            session_token = self.generate_session_token(
                invitation['id'],
                invitation['candidate_email']
            )
            
            # Calculate session expiry
            session_expires_at = datetime.utcnow() + timedelta(
                minutes=test['duration_minutes']
            )
            
            # Create session (use service client)
            session_data = {
                'invitation_id': invitation['id'],
                'test_id': invitation['test_id'],
                'candidate_email': invitation['candidate_email'],
                'candidate_name': invitation['candidate_name'],
                'session_token': session_token,
                'status': 'active',
                'is_active': True,
                'is_completed': False,
                'is_expired': False,
                'can_resume': False,  # Default: no resume
                'started_at': datetime.utcnow().isoformat(),
                'expires_at': session_expires_at.isoformat(),
                'time_remaining_seconds': test['duration_minutes'] * 60,
                'ip_address': ip_address,
                'user_agent': user_agent,
                'browser_info': browser_info,
                'total_marks': test['total_marks'],
                'total_marks_obtained': 0
            }
            
            session_response = self.service_supabase.table('test_sessions') \
                .insert(session_data) \
                .execute()
            
            if not session_response.data:
                raise Exception("Failed to create session")
            
            session = session_response.data[0]
            
            # Mark invitation as used (use service client)
            self.service_supabase.table('test_invitations') \
                .update({'is_used': True}) \
                .eq('id', invitation['id']) \
                .execute()
            
            return {
                'success': True,
                'session': session,
                'resumed': False
            }
            
        except Exception as e:
            logger.error(f"Failed to start session: {str(e)}")
            return {
                'success': False,
                'error': 'Failed to start test session'
            }

    # ============================================
    # Session Validation & Control
    # ============================================

    async def validate_session(self, session_token: str) -> Dict[str, Any]:
        """
        Validate active session
        
        Checks:
        - Session exists
        - Is active
        - Not expired
        - Not completed
        
        Returns:
            Session data if valid
            
        Note: Uses service client to bypass RLS (public endpoint)
        """
        try:
            response = self.service_supabase.table('test_sessions') \
                .select('*') \
                .eq('session_token', session_token) \
                .single() \
                .execute()
            
            if not response.data:
                return {
                    'valid': False,
                    'error': 'Invalid session'
                }
            
            session = response.data
            
            # Check if completed
            if session.get('is_completed'):
                return {
                    'valid': False,
                    'error': 'Test already completed'
                }
            
            # Check if expired
            expires_at = datetime.fromisoformat(session['expires_at'].replace('Z', '+00:00'))
            if datetime.utcnow().replace(tzinfo=expires_at.tzinfo) > expires_at:
                # Auto-expire session
                await self.expire_session(session['id'])
                return {
                    'valid': False,
                    'error': 'Test session expired'
                }
            
            # Update last activity
            await self.update_activity(session['id'])
            
            return {
                'valid': True,
                'session': session
            }
            
        except Exception as e:
            logger.error(f"Session validation failed: {str(e)}")
            return {
                'valid': False,
                'error': 'Session validation failed'
            }

    async def update_activity(self, session_id: str) -> None:
        """Update last activity timestamp"""
        try:
            self.service_supabase.table('test_sessions') \
                .update({
                    'last_activity_at': datetime.utcnow().isoformat()
                }) \
                .eq('id', session_id) \
                .execute()
        except Exception as e:
            logger.error(f"Failed to update activity for session {session_id}: {str(e)}")

    # ============================================
    # Session Termination
    # ============================================

    async def complete_session(self, session_id: str) -> Dict[str, Any]:
        """Mark session as completed (candidate submits test)"""
        try:
            update_data = {
                'status': 'completed',
                'is_active': False,
                'is_completed': True,
                'ended_at': datetime.utcnow().isoformat()
            }
            
            response = self.service_supabase.table('test_sessions') \
                .update(update_data) \
                .eq('id', session_id) \
                .execute()
            
            return {
                'success': True,
                'session': response.data[0] if response.data else None
            }
            
        except Exception as e:
            logger.error(f"Failed to complete session {session_id}: {str(e)}")
            raise

    async def expire_session(self, session_id: str) -> None:
        """Mark session as expired (time limit reached)"""
        try:
            self.supabase.table('test_sessions') \
                .update({
                    'status': 'expired',
                    'is_active': False,
                    'is_expired': True,
                    'ended_at': datetime.utcnow().isoformat()
                }) \
                .eq('id', session_id) \
                .execute()
        except Exception as e:
            logger.error(f"Failed to expire session {session_id}: {str(e)}")

    async def terminate_session(self, session_id: str, reason: str = 'admin_action') -> None:
        """Terminate session (admin action or security violation)"""
        try:
            self.supabase.table('test_sessions') \
                .update({
                    'status': 'terminated',
                    'is_active': False,
                    'ended_at': datetime.utcnow().isoformat(),
                    'admin_comments': reason
                }) \
                .eq('id', session_id) \
                .execute()
        except Exception as e:
            logger.error(f"Failed to terminate session {session_id}: {str(e)}")

    # ============================================
    # Admin Session Reset
    # ============================================

    async def reset_session(
        self,
        invitation_id: str,
        admin_id: str,
        reason: str
    ) -> Dict[str, Any]:
        """
        Admin reset of session (allows candidate to retake)
        
        This:
        - Marks old session as terminated
        - Resets invitation to unused
        - Logs the reset action
        
        Returns:
            Reset confirmation
        """
        try:
            # Get existing session (use service client for admin operations)
            session_response = self.service_supabase.table('test_sessions') \
                .select('*') \
                .eq('invitation_id', invitation_id) \
                .neq('status', 'terminated') \
                .execute()
            
            if session_response.data and len(session_response.data) > 0:
                old_session = session_response.data[0]
                
                # Terminate old session (use service client)
                self.service_supabase.table('test_sessions') \
                    .update({
                        'status': 'terminated',
                        'is_active': False,
                        'admin_comments': f"Reset by admin: {reason}"
                    }) \
                    .eq('id', old_session['id']) \
                    .execute()
            
            # Reset invitation (use service client)
            self.service_supabase.table('test_invitations') \
                .update({'is_used': False}) \
                .eq('id', invitation_id) \
                .execute()
            
            return {
                'success': True,
                'message': 'Session reset successfully. Candidate can now retake the test.'
            }
            
        except Exception as e:
            logger.error(f"Failed to reset session for invitation {invitation_id}: {str(e)}")
            raise

    # ============================================
    # Activity Logging
    # ============================================

    async def log_activity(
        self,
        session_id: str,
        activity_type: str,
        activity_data: Optional[Dict] = None
    ) -> None:
        """Log suspicious or monitoring activity"""
        try:
            log_data = {
                'session_id': session_id,
                'activity_type': activity_type,
                'activity_data': activity_data or {}
            }
            
            # Use service client for unauthenticated candidates
            self.service_supabase.table('session_activity_logs') \
                .insert(log_data) \
                .execute()
            
            # If suspicious activity, increment counter
            if activity_type in ['tab_switch', 'copy_paste', 'copy_attempt', 'paste_attempt', 'fullscreen_exit', 'window_blur', 'multiple_monitors']:
                # Get current count and increment
                session_response = self.service_supabase.table('test_sessions') \
                    .select('suspicious_activity_count') \
                    .eq('id', session_id) \
                    .single() \
                    .execute()
                
                if session_response.data:
                    current_count = session_response.data.get('suspicious_activity_count', 0) or 0
                    self.service_supabase.table('test_sessions') \
                        .update({'suspicious_activity_count': current_count + 1}) \
                        .eq('id', session_id) \
                        .execute()
                    
        except Exception as e:
            logger.error(f"Failed to log activity for session {session_id}: {str(e)}")
