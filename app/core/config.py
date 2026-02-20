"""
Core configuration settings for the application.
Loads environment variables and provides typed settings.
"""
from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import AnyHttpUrl, validator
from pathlib import Path

# Get the directory where this config file is located
BASE_DIR = Path(__file__).resolve().parent.parent.parent
ENV_FILE = BASE_DIR / ".env"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Application
    APP_NAME: str = "Interview Portal"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    ENVIRONMENT: str = "development"
    API_V1_PREFIX: str = "/api/v1"
    
    # Supabase
    SUPABASE_URL: str
    SUPABASE_KEY: str
    SUPABASE_SERVICE_KEY: str
    
    # Security
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # Database
    DATABASE_URL: Optional[str] = None
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_PASSWORD: Optional[str] = None
    
    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:5173", "http://localhost:5174", "http://localhost:3000"]
    
    @validator("CORS_ORIGINS", pre=True)
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v
    
    # Email
    SENDGRID_API_KEY: Optional[str] = None
    FROM_EMAIL: str = "noreply@interviewportal.com"
    FROM_NAME: str = "Interview Portal"
    FRONTEND_URL: str = "http://localhost:5173"
    
    # Code Execution
    PISTON_API_URL: str = "https://emkc.org/api/v2/piston"
    
    # WebRTC
    TURN_SERVER_URL: Optional[str] = None
    TURN_SERVER_USERNAME: Optional[str] = None
    TURN_SERVER_CREDENTIAL: Optional[str] = None
    STUN_SERVER_URL: str = "stun:stun.l.google.com:19302"
    
    # Storage
    STORAGE_BUCKET_RESUMES: str = "resumes"
    STORAGE_BUCKET_RECORDINGS: str = "recordings"
    STORAGE_BUCKET_AVATARS: str = "avatars"
    
    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 60
    
    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"
    
    # Monitoring
    SENTRY_DSN: Optional[str] = None
    
    # Logging
    LOG_LEVEL: str = "INFO"
    
    class Config:
        env_file = str(ENV_FILE)
        case_sensitive = True
        extra = "ignore"


# Create global settings instance
settings = Settings()
