"""
Celery worker configuration for background tasks.
"""
from celery import Celery
from celery.schedules import crontab
from datetime import datetime, timedelta

from app.core.config import settings
from app.core.supabase import get_service_client
from app.services.notification_service import NotificationService

# Create Celery app
celery_app = Celery(
    "interview_portal",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

# Configure Celery
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes
    task_soft_time_limit=25 * 60,  # 25 minutes
    worker_prefetch_multiplier=4,
    worker_max_tasks_per_child=1000,
)


@celery_app.task(name="send_email_notification")
def send_email_notification(email: str, subject: str, body: str):
    """
    Send email notification asynchronously.
    """
    notification_service = NotificationService()
    try:
        notification_service._send_email(email, subject, body)
        return {"success": True, "email": email}
    except Exception as e:
        return {"success": False, "error": str(e)}


@celery_app.task(name="send_interview_reminder")
def send_interview_reminder(interview_id: str):
    """
    Send reminder email 24 hours and 1 hour before interview.
    """
    supabase = get_service_client()
    notification_service = NotificationService()
    
    try:
        # Get interview details
        result = (
            supabase.table("interviews")
            .select("*, candidates(*), users!interviewer_id(*)")
            .eq("id", interview_id)
            .single()
            .execute()
        )
        
        if not result.data:
            return {"success": False, "error": "Interview not found"}
        
        interview = result.data
        candidate = interview.get("candidates")
        interviewer = interview.get("users")
        
        # Send to candidate
        if candidate:
            notification_service.send_interview_reminder_email(
                candidate["email"],
                interview,
                "24 hours"
            )
        
        # Send to interviewer
        if interviewer:
            notification_service.send_interview_reminder_email(
                interviewer["email"],
                interview,
                "24 hours"
            )
        
        return {"success": True, "interview_id": interview_id}
    
    except Exception as e:
        return {"success": False, "error": str(e)}


@celery_app.task(name="cleanup_old_recordings")
def cleanup_old_recordings():
    """
    Delete recordings older than 90 days (configurable).
    """
    supabase = get_service_client()
    
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=90)
        
        # Get old recordings
        result = (
            supabase.table("interview_recordings")
            .select("id, storage_path")
            .lt("created_at", cutoff_date.isoformat())
            .execute()
        )
        
        deleted_count = 0
        for recording in result.data:
            # Delete from storage
            try:
                supabase.storage.from_("recordings").remove([recording["storage_path"]])
            except Exception:
                pass  # Continue even if file doesn't exist
            
            # Delete record
            supabase.table("interview_recordings").delete().eq("id", recording["id"]).execute()
            deleted_count += 1
        
        return {"success": True, "deleted_count": deleted_count}
    
    except Exception as e:
        return {"success": False, "error": str(e)}


@celery_app.task(name="cleanup_old_code_snapshots")
def cleanup_old_code_snapshots():
    """
    Delete code snapshots older than 30 days.
    """
    supabase = get_service_client()
    
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=30)
        
        result = (
            supabase.table("code_snapshots")
            .delete()
            .lt("created_at", cutoff_date.isoformat())
            .execute()
        )
        
        deleted_count = len(result.data) if result.data else 0
        
        return {"success": True, "deleted_count": deleted_count}
    
    except Exception as e:
        return {"success": False, "error": str(e)}


@celery_app.task(name="generate_daily_report")
def generate_daily_report():
    """
    Generate and send daily report to admins.
    """
    supabase = get_service_client()
    notification_service = NotificationService()
    
    try:
        # Get yesterday's date range
        yesterday = datetime.utcnow().date() - timedelta(days=1)
        start_date = datetime.combine(yesterday, datetime.min.time())
        end_date = datetime.combine(yesterday, datetime.max.time())
        
        # Get statistics
        interviews_result = (
            supabase.table("interviews")
            .select("*", count="exact")
            .gte("created_at", start_date.isoformat())
            .lte("created_at", end_date.isoformat())
            .execute()
        )
        
        candidates_result = (
            supabase.table("candidates")
            .select("*", count="exact")
            .gte("created_at", start_date.isoformat())
            .lte("created_at", end_date.isoformat())
            .execute()
        )
        
        # Get all admins
        admins_result = (
            supabase.table("users")
            .select("email")
            .eq("role", "admin")
            .execute()
        )
        
        # Generate report
        report = f"""
        Daily Interview Portal Report - {yesterday.strftime('%B %d, %Y')}
        
        📅 Interviews Scheduled: {interviews_result.count or 0}
        👤 New Candidates Added: {candidates_result.count or 0}
        
        Have a great day!
        """
        
        # Send to all admins
        for admin in admins_result.data:
            notification_service._send_email(
                admin["email"],
                f"Daily Report - {yesterday.strftime('%B %d, %Y')}",
                report
            )
        
        return {"success": True, "date": yesterday.isoformat()}
    
    except Exception as e:
        return {"success": False, "error": str(e)}


@celery_app.task(name="update_interview_status")
def update_interview_status():
    """
    Update interview status from 'scheduled' to 'completed' if end time has passed.
    """
    supabase = get_service_client()
    
    try:
        now = datetime.utcnow()
        
        # Get interviews that should be marked as completed
        result = (
            supabase.table("interviews")
            .select("id, end_time")
            .eq("status", "scheduled")
            .lt("end_time", now.isoformat())
            .execute()
        )
        
        updated_count = 0
        for interview in result.data:
            supabase.table("interviews").update(
                {"status": "completed"}
            ).eq("id", interview["id"]).execute()
            updated_count += 1
        
        return {"success": True, "updated_count": updated_count}
    
    except Exception as e:
        return {"success": False, "error": str(e)}


# Celery Beat Schedule for periodic tasks
celery_app.conf.beat_schedule = {
    # Send interview reminders every hour
    "send-interview-reminders": {
        "task": "send_interview_reminder",
        "schedule": crontab(minute=0),  # Every hour
    },
    # Cleanup old recordings every day at 2 AM
    "cleanup-old-recordings": {
        "task": "cleanup_old_recordings",
        "schedule": crontab(hour=2, minute=0),
    },
    # Cleanup old code snapshots every day at 3 AM
    "cleanup-old-code-snapshots": {
        "task": "cleanup_old_code_snapshots",
        "schedule": crontab(hour=3, minute=0),
    },
    # Generate daily report at 8 AM
    "generate-daily-report": {
        "task": "generate_daily_report",
        "schedule": crontab(hour=8, minute=0),
    },
    # Update interview status every 15 minutes
    "update-interview-status": {
        "task": "update_interview_status",
        "schedule": crontab(minute="*/15"),  # Every 15 minutes
    },
}


if __name__ == "__main__":
    celery_app.start()
