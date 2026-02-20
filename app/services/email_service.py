"""
Email service for sending interview notifications and reminders.
"""
import os
import logging
from typing import List, Optional
from datetime import datetime
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmailService:
    """Service for sending emails via SendGrid."""
    
    def __init__(self):
        """Initialize SendGrid client."""
        self.client = None
        if settings.SENDGRID_API_KEY and settings.SENDGRID_API_KEY != "your_sendgrid_api_key":
            try:
                self.client = SendGridAPIClient(settings.SENDGRID_API_KEY)
            except Exception as e:
                logger.warning(f"SendGrid initialization failed: {e}")
                logger.warning("Email notifications will be logged but not sent")
    
    def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        from_email: Optional[str] = None
    ) -> bool:
        """
        Send an email.
        
        Args:
            to_email: Recipient email address
            subject: Email subject
            html_content: HTML content of the email
            from_email: Sender email (optional, uses default)
            
        Returns:
            True if email was sent successfully, False otherwise
        """
        if not self.client:
            logger.info(f"[MOCK EMAIL] To: {to_email}, Subject: {subject}")
            logger.info(f"[MOCK EMAIL] Content: {html_content[:200]}...")
            return True
        
        try:
            from_email = from_email or settings.FROM_EMAIL
            message = Mail(
                from_email=Email(from_email, settings.FROM_NAME),
                to_emails=To(to_email),
                subject=subject,
                html_content=Content("text/html", html_content)
            )
            
            response = self.client.send(message)
            
            if response.status_code in [200, 201, 202]:
                logger.info(f"Email sent successfully to {to_email}")
                return True
            else:
                logger.error(f"Failed to send email to {to_email}. Status: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending email to {to_email}: {str(e)}")
            return False
    
    def send_interview_invitation(
        self,
        candidate_email: str,
        candidate_name: str,
        interviewer_name: str,
        interview_id: str,
        scheduled_time: datetime,
        position: str,
        meeting_link: str
    ) -> bool:
        """
        Send interview invitation to candidate.
        
        Args:
            candidate_email: Candidate's email
            candidate_name: Candidate's name
            interviewer_name: Interviewer's name
            interview_id: Interview ID
            scheduled_time: Scheduled interview time
            position: Position being interviewed for
            meeting_link: Link to join the interview
            
        Returns:
            True if email was sent successfully
        """
        subject = f"Interview Scheduled - {position}"
        
        formatted_time = scheduled_time.strftime("%B %d, %Y at %I:%M %p")
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                }}
                .container {{
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                    background-color: #f9f9f9;
                }}
                .header {{
                    background-color: #4F46E5;
                    color: white;
                    padding: 20px;
                    text-align: center;
                    border-radius: 8px 8px 0 0;
                }}
                .content {{
                    background-color: white;
                    padding: 30px;
                    border-radius: 0 0 8px 8px;
                }}
                .button {{
                    display: inline-block;
                    padding: 12px 30px;
                    background-color: #4F46E5;
                    color: white;
                    text-decoration: none;
                    border-radius: 6px;
                    margin: 20px 0;
                }}
                .info-box {{
                    background-color: #f0f0f0;
                    padding: 15px;
                    border-left: 4px solid #4F46E5;
                    margin: 20px 0;
                }}
                .footer {{
                    text-align: center;
                    margin-top: 20px;
                    font-size: 12px;
                    color: #666;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🎯 Interview Scheduled</h1>
                </div>
                <div class="content">
                    <p>Dear {candidate_name},</p>
                    
                    <p>Your interview for the position of <strong>{position}</strong> has been scheduled!</p>
                    
                    <div class="info-box">
                        <h3>📋 Interview Details</h3>
                        <p><strong>Position:</strong> {position}</p>
                        <p><strong>Interviewer:</strong> {interviewer_name}</p>
                        <p><strong>Date & Time:</strong> {formatted_time}</p>
                        <p><strong>Interview ID:</strong> {interview_id}</p>
                    </div>
                    
                    <h3>🎥 Joining the Interview</h3>
                    <p>Click the button below to join your interview at the scheduled time:</p>
                    
                    <center>
                        <a href="{meeting_link}" class="button">Join Interview</a>
                    </center>
                    
                    <div class="info-box">
                        <h3>📝 Important Notes</h3>
                        <ul>
                            <li>Your camera and microphone will be enabled when you join</li>
                            <li>Screen sharing will be required for the coding session</li>
                            <li>The interview includes a collaborative code editor with multiple programming languages</li>
                            <li>Please join 5 minutes early to test your setup</li>
                            <li>Ensure stable internet connection</li>
                        </ul>
                    </div>
                    
                    <h3>💻 Technical Requirements</h3>
                    <ul>
                        <li>Modern web browser (Chrome, Firefox, Edge, Safari)</li>
                        <li>Working webcam and microphone</li>
                        <li>Stable internet connection (minimum 5 Mbps)</li>
                        <li>Quiet environment with good lighting</li>
                    </ul>
                    
                    <p>If you have any questions or need to reschedule, please contact us immediately.</p>
                    
                    <p>Good luck!</p>
                    
                    <p>Best regards,<br>
                    <strong>Interview Portal Team</strong></p>
                </div>
                <div class="footer">
                    <p>This is an automated email. Please do not reply directly to this message.</p>
                    <p>&copy; 2026 Interview Portal. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return self.send_email(candidate_email, subject, html_content)
    
    def send_interviewer_notification(
        self,
        interviewer_email: str,
        interviewer_name: str,
        candidate_name: str,
        interview_id: str,
        scheduled_time: datetime,
        position: str,
        meeting_link: str
    ) -> bool:
        """
        Send notification to interviewer about scheduled interview.
        
        Args:
            interviewer_email: Interviewer's email
            interviewer_name: Interviewer's name
            candidate_name: Candidate's name
            interview_id: Interview ID
            scheduled_time: Scheduled interview time
            position: Position being interviewed for
            meeting_link: Link to join the interview
            
        Returns:
            True if email was sent successfully
        """
        subject = f"New Interview Assigned - {candidate_name}"
        
        formatted_time = scheduled_time.strftime("%B %d, %Y at %I:%M %p")
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                }}
                .container {{
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                    background-color: #f9f9f9;
                }}
                .header {{
                    background-color: #059669;
                    color: white;
                    padding: 20px;
                    text-align: center;
                    border-radius: 8px 8px 0 0;
                }}
                .content {{
                    background-color: white;
                    padding: 30px;
                    border-radius: 0 0 8px 8px;
                }}
                .button {{
                    display: inline-block;
                    padding: 12px 30px;
                    background-color: #059669;
                    color: white;
                    text-decoration: none;
                    border-radius: 6px;
                    margin: 20px 0;
                }}
                .info-box {{
                    background-color: #f0f0f0;
                    padding: 15px;
                    border-left: 4px solid #059669;
                    margin: 20px 0;
                }}
                .footer {{
                    text-align: center;
                    margin-top: 20px;
                    font-size: 12px;
                    color: #666;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>👔 New Interview Assigned</h1>
                </div>
                <div class="content">
                    <p>Dear {interviewer_name},</p>
                    
                    <p>You have been assigned to conduct an interview for <strong>{candidate_name}</strong>.</p>
                    
                    <div class="info-box">
                        <h3>📋 Interview Details</h3>
                        <p><strong>Candidate:</strong> {candidate_name}</p>
                        <p><strong>Position:</strong> {position}</p>
                        <p><strong>Date & Time:</strong> {formatted_time}</p>
                        <p><strong>Interview ID:</strong> {interview_id}</p>
                    </div>
                    
                    <center>
                        <a href="{meeting_link}" class="button">Join Interview Room</a>
                    </center>
                    
                    <div class="info-box">
                        <h3>🎯 Interviewer Features</h3>
                        <ul>
                            <li>Video conferencing with picture-in-picture mode</li>
                            <li>Real-time collaborative code editor</li>
                            <li>Multiple programming language support</li>
                            <li>Code execution and testing capabilities</li>
                            <li>Automatic tab synchronization with candidate</li>
                            <li>Screen monitoring for candidate activity</li>
                        </ul>
                    </div>
                    
                    <p>The platform will automatically:</p>
                    <ul>
                        <li>Enable candidate's camera, mic, and screen sharing</li>
                        <li>Switch candidate's view when you change tabs</li>
                        <li>Show candidate in picture-in-picture during coding</li>
                        <li>Sync code edits in real-time</li>
                    </ul>
                    
                    <p>Best regards,<br>
                    <strong>Interview Portal Team</strong></p>
                </div>
                <div class="footer">
                    <p>This is an automated email. Please do not reply directly to this message.</p>
                    <p>&copy; 2026 Interview Portal. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return self.send_email(interviewer_email, subject, html_content)
    
    async def send_test_invitation(
        self,
        candidate_email: str,
        candidate_name: str,
        test_title: str,
        test_duration: int,
        invitation_url: str,
        expires_at: str
    ) -> bool:
        """
        Send coding test invitation to candidate.
        
        Args:
            candidate_email: Candidate's email
            candidate_name: Candidate's name
            test_title: Title of the test
            test_duration: Duration in minutes
            invitation_url: Unique link to start the test
            expires_at: Expiration time
            
        Returns:
            True if email was sent successfully
        """
        subject = f"Coding Assessment Invitation - {test_title}"
        
        try:
            expires_datetime = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
            expires_formatted = expires_datetime.strftime("%B %d, %Y at %I:%M %p")
        except:
            expires_formatted = expires_at
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                }}
                .container {{
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                    background-color: #f9f9f9;
                }}
                .header {{
                    background-color: #059669;
                    color: white;
                    padding: 20px;
                    text-align: center;
                    border-radius: 8px 8px 0 0;
                }}
                .content {{
                    background-color: white;
                    padding: 30px;
                    border-radius: 0 0 8px 8px;
                }}
                .button {{
                    display: inline-block;
                    padding: 15px 40px;
                    background-color: #059669;
                    color: white;
                    text-decoration: none;
                    border-radius: 6px;
                    margin: 20px 0;
                    font-weight: bold;
                    font-size: 16px;
                }}
                .info-box {{
                    background-color: #f0fdf4;
                    padding: 15px;
                    border-left: 4px solid #059669;
                    margin: 20px 0;
                }}
                .warning-box {{
                    background-color: #fef3c7;
                    padding: 15px;
                    border-left: 4px solid #f59e0b;
                    margin: 20px 0;
                }}
                .footer {{
                    text-align: center;
                    margin-top: 20px;
                    font-size: 12px;
                    color: #666;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>💻 Coding Assessment Invitation</h1>
                </div>
                <div class="content">
                    <p>Dear {candidate_name},</p>
                    
                    <p>You've been invited to complete a coding assessment for our hiring process.</p>
                    
                    <div class="info-box">
                        <h3>📝 Test Details</h3>
                        <p><strong>Test:</strong> {test_title}</p>
                        <p><strong>Duration:</strong> {test_duration} minutes</p>
                        <p><strong>Link Expires:</strong> {expires_formatted}</p>
                        <p><strong>Format:</strong> Auto-graded coding questions + manual review</p>
                    </div>
                    
                    <div class="warning-box">
                        <h3>⚠️ Important: One-Time Access</h3>
                        <p><strong>This test can only be taken ONCE.</strong> Once you click "Start Test", the session will begin and cannot be restarted. Make sure you're ready before starting!</p>
                    </div>
                    
                    <h3>🚀 Ready to Start?</h3>
                    <p>Click the button below to begin your assessment:</p>
                    
                    <center>
                        <a href="{invitation_url}" class="button">Start Coding Test</a>
                    </center>
                    
                    <h3>📋 What to Expect</h3>
                    <ul>
                        <li><strong>Question Types:</strong> SQL, Python, JavaScript, MCQs, and descriptive questions</li>
                        <li><strong>Auto-Grading:</strong> Most questions are automatically evaluated</li>
                        <li><strong>Code Execution:</strong> Your code runs against test cases in real-time</li>
                        <li><strong>Session Control:</strong> Timer starts when you begin, cannot be paused</li>
                        <li><strong>Auto-Submit:</strong> Test auto-submits when time expires</li>
                    </ul>
                    
                    <h3>💻 Technical Requirements</h3>
                    <ul>
                        <li>Modern web browser (Chrome, Firefox, Edge recommended)</li>
                        <li>Stable internet connection</li>
                        <li>Quiet environment with minimal distractions</li>
                        <li>Disable pop-up blockers</li>
                    </ul>
                    
                    <h3>📚 Preparation Tips</h3>
                    <ul>
                        <li>Review the programming languages you'll be tested on</li>
                        <li>Practice writing clean, efficient code</li>
                        <li>Allocate enough uninterrupted time ({test_duration} minutes)</li>
                        <li>Test your internet connection beforehand</li>
                        <li>Have a backup device ready in case of technical issues</li>
                    </ul>
                    
                    <div class="warning-box">
                        <h3>🔒 Session Rules</h3>
                        <ul>
                            <li>Your activity will be monitored (tab switches, time spent per question)</li>
                            <li>Do not close or refresh the browser during the test</li>
                            <li>Submit each answer before moving to the next question</li>
                            <li>Once submitted, answers cannot be changed</li>
                            <li>Test must be completed in one sitting</li>
                        </ul>
                    </div>
                    
                    <p>Good luck with your assessment! If you face any technical issues during the test, please contact our support team immediately.</p>
                    
                    <p>Best regards,<br>
                    <strong>Hiring Team</strong></p>
                </div>
                <div class="footer">
                    <p>This invitation is unique to you. Do not share this link with anyone.</p>
                    <p>&copy; 2026 Interview Portal. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return self.send_email(candidate_email, subject, html_content)


# Singleton instance
email_service = EmailService()
