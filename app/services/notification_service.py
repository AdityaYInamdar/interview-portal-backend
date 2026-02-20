"""
Notification Service - Handles email and in-app notifications.
"""
from typing import Dict, Any, Optional
from datetime import datetime
import httpx
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

from app.core.config import settings
from app.schemas.common import NotificationType, NotificationCreate


class NotificationService:
    """Service for sending notifications."""
    
    def __init__(self, supabase_client):
        self.db = supabase_client
        self.sendgrid_client = None
        if settings.SENDGRID_API_KEY:
            self.sendgrid_client = SendGridAPIClient(settings.SENDGRID_API_KEY)
    
    async def send_interview_scheduled_notification(self, interview: Dict[str, Any]):
        """Send notification when interview is scheduled."""
        # Get candidate and interviewer details
        candidate = self.db.table("candidates").select("*").eq("id", interview["candidate_id"]).execute()
        interviewer = self.db.table("users").select("*").eq("id", interview["interviewer_id"]).execute()
        
        if not candidate.data or not interviewer.data:
            return
        
        candidate_data = candidate.data[0]
        interviewer_data = interviewer.data[0]
        
        # Create scheduled datetime string
        scheduled_time = datetime.fromisoformat(interview["scheduled_at"].replace("Z", "+00:00"))
        formatted_time = scheduled_time.strftime("%B %d, %Y at %I:%M %p")
        
        # Send to candidate
        await self._send_email(
            to_email=candidate_data["email"],
            to_name=candidate_data["full_name"],
            subject=f"Interview Scheduled: {interview['position']}",
            html_content=self._get_interview_scheduled_email(
                candidate_name=candidate_data["full_name"],
                position=interview["position"],
                scheduled_time=formatted_time,
                duration=interview["duration_minutes"],
                interviewer_name=interviewer_data["full_name"],
                meeting_url=interview["meeting_url"]
            )
        )
        
        # Create in-app notification for candidate
        if candidate_data.get("user_id"):
            await self.create_notification(NotificationCreate(
                user_id=candidate_data["user_id"],
                notification_type=NotificationType.INTERVIEW_SCHEDULED,
                title="Interview Scheduled",
                message=f"Your interview for {interview['position']} is scheduled for {formatted_time}",
                data={"interview_id": interview["id"]},
                send_email=False
            ))
        
        # Send to interviewer
        await self._send_email(
            to_email=interviewer_data["email"],
            to_name=interviewer_data["full_name"],
            subject=f"Interview Assigned: {interview['position']}",
            html_content=self._get_interviewer_assigned_email(
                interviewer_name=interviewer_data["full_name"],
                candidate_name=candidate_data["full_name"],
                position=interview["position"],
                scheduled_time=formatted_time,
                duration=interview["duration_minutes"],
                meeting_url=interview["meeting_url"]
            )
        )
        
        # Create in-app notification for interviewer
        await self.create_notification(NotificationCreate(
            user_id=interviewer_data["id"],
            notification_type=NotificationType.INTERVIEW_SCHEDULED,
            title="Interview Assigned",
            message=f"You have been assigned to interview {candidate_data['full_name']} for {interview['position']}",
            data={"interview_id": interview["id"]},
            send_email=False
        ))
    
    async def send_interview_rescheduled_notification(self, interview_id: str):
        """Send notification when interview is rescheduled."""
        interview = self.db.table("interviews").select("*").eq("id", interview_id).execute()
        
        if interview.data:
            await self.send_interview_scheduled_notification(interview.data[0])
    
    async def send_interview_cancelled_notification(self, interview_id: str):
        """Send notification when interview is cancelled."""
        interview = self.db.table("interviews").select("*").eq("id", interview_id).execute()
        
        if not interview.data:
            return
        
        interview_data = interview.data[0]
        
        # Get candidate and interviewer
        candidate = self.db.table("candidates").select("*").eq("id", interview_data["candidate_id"]).execute()
        interviewer = self.db.table("users").select("*").eq("id", interview_data["interviewer_id"]).execute()
        
        if candidate.data:
            candidate_data = candidate.data[0]
            await self._send_email(
                to_email=candidate_data["email"],
                to_name=candidate_data["full_name"],
                subject=f"Interview Cancelled: {interview_data['position']}",
                html_content=f"<p>Your interview for {interview_data['position']} has been cancelled. We will reach out to reschedule.</p>"
            )
        
        if interviewer.data:
            interviewer_data = interviewer.data[0]
            await self._send_email(
                to_email=interviewer_data["email"],
                to_name=interviewer_data["full_name"],
                subject=f"Interview Cancelled: {interview_data['position']}",
                html_content=f"<p>The interview with {candidate_data['full_name']} has been cancelled.</p>"
            )
    
    async def send_evaluation_submitted_notification(self, evaluation_id: str):
        """Send notification when evaluation is submitted."""
        evaluation = self.db.table("evaluations").select("*").eq("id", evaluation_id).execute()
        
        if not evaluation.data:
            return
        
        evaluation_data = evaluation.data[0]
        interview = self.db.table("interviews").select("*").eq("id", evaluation_data["interview_id"]).execute()
        
        if not interview.data:
            return
        
        interview_data = interview.data[0]
        
        # Notify admin
        company_admins = self.db.table("users").select("*").eq("company_id", interview_data["company_id"]).eq("role", "admin").execute()
        
        for admin in company_admins.data:
            await self.create_notification(NotificationCreate(
                user_id=admin["id"],
                notification_type=NotificationType.EVALUATION_SUBMITTED,
                title="Evaluation Submitted",
                message=f"Interview evaluation has been submitted for {interview_data['position']}",
                data={"interview_id": interview_data["id"], "evaluation_id": evaluation_id},
                send_email=True
            ))
    
    async def create_notification(self, notification: NotificationCreate):
        """Create an in-app notification."""
        notification_dict = notification.model_dump()
        
        # Extract send_email flag (not a database column)
        should_send_email = notification_dict.pop('send_email', True)
        
        result = self.db.table("notifications").insert(notification_dict).execute()
        
        if should_send_email and result.data:
            # Get user email
            user = self.db.table("users").select("email, full_name").eq("id", notification.user_id).execute()
            if user.data:
                await self._send_email(
                    to_email=user.data[0]["email"],
                    to_name=user.data[0]["full_name"],
                    subject=notification.title,
                    html_content=f"<p>{notification.message}</p>"
                )
        
        return result.data[0] if result.data else None
    
    async def _send_email(
        self,
        to_email: str,
        to_name: str,
        subject: str,
        html_content: str
    ):
        """Send email via SendGrid."""
        if not self.sendgrid_client:
            print(f"Email not sent (no SendGrid API key): {to_email} - {subject}")
            return
        
        try:
            message = Mail(
                from_email=(settings.FROM_EMAIL, settings.FROM_NAME),
                to_emails=(to_email, to_name),
                subject=subject,
                html_content=html_content
            )
            
            response = self.sendgrid_client.send(message)
            return response
        except Exception as e:
            print(f"Failed to send email: {str(e)}")
            return None
    
    def _get_interview_scheduled_email(
        self,
        candidate_name: str,
        position: str,
        scheduled_time: str,
        duration: int,
        interviewer_name: str,
        meeting_url: str
    ) -> str:
        """Get HTML template for interview scheduled email."""
        # Build absolute URL - meeting_url is like /interview/room_xxxxxxxx
        frontend_base = getattr(settings, 'FRONTEND_URL', 'http://localhost:5173')
        full_meeting_url = f"{frontend_base.rstrip('/')}{meeting_url}"
        return f"""
        <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; background-color: #f9fafb;">
                <div style="max-width: 620px; margin: 30px auto; background: #fff; border-radius: 10px; overflow: hidden; box-shadow: 0 2px 12px rgba(0,0,0,0.08);">
                    <!-- Header -->
                    <div style="background: linear-gradient(135deg, #4F46E5, #7C3AED); padding: 32px 40px;">
                        <h1 style="color: #fff; margin: 0; font-size: 24px;">🎯 Interview Scheduled</h1>
                        <p style="color: rgba(255,255,255,0.85); margin: 8px 0 0;">Your interview has been confirmed</p>
                    </div>
                    <!-- Body -->
                    <div style="padding: 32px 40px;">
                        <p style="font-size: 16px;">Hi <strong>{candidate_name}</strong>,</p>
                        <p>Great news! Your interview has been scheduled. Here are all the details you need:</p>

                        <div style="background: #F3F4F6; border-left: 4px solid #4F46E5; padding: 20px 24px; border-radius: 6px; margin: 24px 0;">
                            <table style="width:100%; border-collapse: collapse;">
                                <tr><td style="padding: 6px 0; color: #6B7280; width: 140px;">Position</td><td style="padding: 6px 0; font-weight: 600;">{position}</td></tr>
                                <tr><td style="padding: 6px 0; color: #6B7280;">Date &amp; Time</td><td style="padding: 6px 0; font-weight: 600;">{scheduled_time}</td></tr>
                                <tr><td style="padding: 6px 0; color: #6B7280;">Duration</td><td style="padding: 6px 0; font-weight: 600;">{duration} minutes</td></tr>
                                <tr><td style="padding: 6px 0; color: #6B7280;">Interviewer</td><td style="padding: 6px 0; font-weight: 600;">{interviewer_name}</td></tr>
                                <tr><td style="padding: 6px 0; color: #6B7280;">Platform</td><td style="padding: 6px 0; font-weight: 600;">Interview Portal (Online)</td></tr>
                            </table>
                        </div>

                        <!-- Join Button -->
                        <div style="text-align: center; margin: 32px 0;">
                            <a href="{full_meeting_url}" style="background: #4F46E5; color: #fff; padding: 14px 36px; text-decoration: none; border-radius: 8px; font-size: 16px; font-weight: 600; display: inline-block; letter-spacing: 0.3px;">
                                🚀 Join Interview Room
                            </a>
                            <p style="margin-top: 12px; font-size: 13px; color: #6B7280;">Or copy this link: <a href="{full_meeting_url}" style="color: #4F46E5;">{full_meeting_url}</a></p>
                        </div>

                        <!-- Technical Requirements -->
                        <div style="background: #FFF7ED; border: 1px solid #FED7AA; border-radius: 8px; padding: 20px 24px; margin: 24px 0;">
                            <h3 style="margin: 0 0 12px; color: #C2410C; font-size: 15px;">⚠️ Important: Technical Requirements</h3>
                            <p style="margin: 0 0 10px; font-size: 14px;">When you join the interview, your browser will request the following permissions — please <strong>allow all of them</strong>:</p>
                            <ul style="margin: 0; padding-left: 20px; font-size: 14px; line-height: 1.8;">
                                <li>📷 <strong>Camera</strong> — must be enabled throughout</li>
                                <li>🎤 <strong>Microphone</strong> — must be enabled throughout</li>
                                <li>🖥️ <strong>Screen Sharing</strong> — you will be asked to share your entire screen</li>
                            </ul>
                            <p style="margin: 12px 0 0; font-size: 13px; color: #9A3412;">The interview room uses a built-in video meeting — no Zoom or Google Meet needed.</p>
                        </div>

                        <!-- Checklist -->
                        <h3 style="font-size: 15px; margin-bottom: 10px;">✅ Before the Interview</h3>
                        <ul style="padding-left: 20px; font-size: 14px; line-height: 2;">
                            <li>Test your camera and microphone</li>
                            <li>Use a modern browser (Chrome or Firefox recommended)</li>
                            <li>Ensure a stable, fast internet connection</li>
                            <li>Choose a quiet, well-lit environment</li>
                            <li>Close unnecessary applications</li>
                            <li>Join <strong>5 minutes early</strong></li>
                        </ul>

                        <p style="margin-top: 28px;">Good luck — we're rooting for you! 🌟</p>
                        <p>Best regards,<br><strong>Interview Portal Team</strong></p>
                    </div>
                    <!-- Footer -->
                    <div style="background: #F3F4F6; padding: 16px 40px; text-align: center; font-size: 12px; color: #9CA3AF;">
                        This is an automated message. Please do not reply to this email.
                    </div>
                </div>
            </body>
        </html>
        """
    
    def _get_interviewer_assigned_email(
        self,
        interviewer_name: str,
        candidate_name: str,
        position: str,
        scheduled_time: str,
        duration: int,
        meeting_url: str
    ) -> str:
        """Get HTML template for interviewer assignment email."""
        frontend_base = getattr(settings, 'FRONTEND_URL', 'http://localhost:5173')
        full_meeting_url = f"{frontend_base.rstrip('/')}{meeting_url}"
        return f"""
        <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; background-color: #f9fafb;">
                <div style="max-width: 620px; margin: 30px auto; background: #fff; border-radius: 10px; overflow: hidden; box-shadow: 0 2px 12px rgba(0,0,0,0.08);">
                    <div style="background: linear-gradient(135deg, #059669, #047857); padding: 32px 40px;">
                        <h1 style="color: #fff; margin: 0; font-size: 24px;">📋 Interview Assigned</h1>
                        <p style="color: rgba(255,255,255,0.85); margin: 8px 0 0;">You have a new interview to conduct</p>
                    </div>
                    <div style="padding: 32px 40px;">
                        <p style="font-size: 16px;">Hi <strong>{interviewer_name}</strong>,</p>
                        <p>You have been assigned to conduct the following interview:</p>

                        <div style="background: #F3F4F6; border-left: 4px solid #059669; padding: 20px 24px; border-radius: 6px; margin: 24px 0;">
                            <table style="width:100%; border-collapse: collapse;">
                                <tr><td style="padding: 6px 0; color: #6B7280; width: 140px;">Candidate</td><td style="padding: 6px 0; font-weight: 600;">{candidate_name}</td></tr>
                                <tr><td style="padding: 6px 0; color: #6B7280;">Position</td><td style="padding: 6px 0; font-weight: 600;">{position}</td></tr>
                                <tr><td style="padding: 6px 0; color: #6B7280;">Date &amp; Time</td><td style="padding: 6px 0; font-weight: 600;">{scheduled_time}</td></tr>
                                <tr><td style="padding: 6px 0; color: #6B7280;">Duration</td><td style="padding: 6px 0; font-weight: 600;">{duration} minutes</td></tr>
                            </table>
                        </div>

                        <div style="text-align: center; margin: 32px 0;">
                            <a href="{full_meeting_url}" style="background: #059669; color: #fff; padding: 14px 36px; text-decoration: none; border-radius: 8px; font-size: 16px; font-weight: 600; display: inline-block;">
                                🎙️ Open Interview Room
                            </a>
                            <p style="margin-top: 12px; font-size: 13px; color: #6B7280;">Room link: <a href="{full_meeting_url}" style="color: #059669;">{full_meeting_url}</a></p>
                        </div>

                        <p>As the interviewer you are the <strong>room controller</strong>. You can switch between the Meeting and Coding tabs — the candidate's screen will follow your tab automatically.</p>
                        <p>Please review the candidate's profile and prepare your questions before the interview.</p>
                        <p>Best regards,<br><strong>Interview Portal Team</strong></p>
                    </div>
                    <div style="background: #F3F4F6; padding: 16px 40px; text-align: center; font-size: 12px; color: #9CA3AF;">
                        This is an automated message. Please do not reply to this email.
                    </div>
                </div>
            </body>
        </html>
        """
