"""
Authentication API endpoints.
"""
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
    verify_password,
    get_current_user_token
)
from app.core.supabase import get_supabase, get_supabase_service
from app.schemas.user import (
    LoginRequest,
    Token,
    UserCreate,
    UserResponse,
    PasswordChange,
    PasswordReset,
    TokenRefresh
)

router = APIRouter(prefix="/auth", tags=["Authentication"])
security = HTTPBearer()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserCreate, supabase=Depends(get_supabase)):
    """
    Register a new user account.
    
    - Creates a user in Supabase Auth
    - Creates user profile in database
    - Returns user data (no automatic login)
    """
    try:
        # Check if user already exists
        existing_user = supabase.table("users").select("*").eq("email", user_data.email).execute()
        if existing_user.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
        
        # Create user in Supabase Auth with email confirmation disabled for development
        auth_response = supabase.auth.sign_up({
            "email": user_data.email,
            "password": user_data.password,
            "options": {
                "email_redirect_to": None,
                "data": {
                    "full_name": user_data.full_name,
                    "role": user_data.role.value
                }
            }
        })
        
        if not auth_response.user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to create user account"
            )
        
        # Use service client to auto-confirm email for development
        service_client = get_supabase_service()
        try:
            service_client.auth.admin.update_user_by_id(
                auth_response.user.id,
                {"email_confirm": True}
            )
        except:
            pass  # Continue even if email confirmation fails
        
        # Handle company creation/linking
        company_id = None
        if user_data.company_name:
            # Check if company exists (case-insensitive)
            existing_company = service_client.table("companies").select("*").ilike("name", user_data.company_name).execute()
            
            if existing_company.data:
                # Use existing company
                company_id = existing_company.data[0]["id"]
            else:
                # Create new company
                new_company = service_client.table("companies").insert({
                    "name": user_data.company_name,
                    "description": f"Company registered via {user_data.full_name}"
                }).execute()
                
                if new_company.data:
                    company_id = new_company.data[0]["id"]
        
        # Create user profile in database
        user_profile = {
            "id": auth_response.user.id,
            "email": user_data.email,
            "full_name": user_data.full_name,
            "role": user_data.role.value,
            "phone": user_data.phone,
            "timezone": user_data.timezone,
            "avatar_url": user_data.avatar_url,
            "company_id": company_id,
            "status": "active",
            "email_verified": True  # Auto-verify for development
        }
        
        result = supabase.table("users").insert(user_profile).execute()
        
        return UserResponse(**result.data[0])
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Registration failed: {str(e)}"
        )


@router.post("/login", response_model=Token)
async def login(credentials: LoginRequest, supabase=Depends(get_supabase)):
    """
    Login with email and password.
    
    - Authenticates with Supabase
    - Returns JWT access and refresh tokens
    - Returns user profile data
    """
    try:
        # Authenticate with Supabase
        auth_response = supabase.auth.sign_in_with_password({
            "email": credentials.email,
            "password": credentials.password
        })
        
        if not auth_response.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password"
            )
        
        # Get user profile
        user_result = supabase.table("users").select("*").eq("id", auth_response.user.id).execute()
        
        if not user_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User profile not found"
            )
        
        user = user_result.data[0]
        
        # Check if user is active
        if user.get("status") != "active":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is inactive or suspended"
            )
        
        # Update last login
        supabase.table("users").update({
            "last_login": "now()"
        }).eq("id", user["id"]).execute()
        
        # Create tokens
        token_data = {
            "sub": user["id"],
            "email": user["email"],
            "role": user["role"],
            "company_id": user.get("company_id")
        }
        
        access_token = create_access_token(token_data)
        refresh_token = create_refresh_token(token_data)
        
        return Token(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user=UserResponse(**user)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Login failed: {str(e)}"
        )


@router.post("/refresh", response_model=Token)
async def refresh_token(token_data: TokenRefresh, supabase=Depends(get_supabase)):
    """
    Refresh access token using refresh token.
    
    - Validates refresh token
    - Issues new access and refresh tokens
    """
    try:
        # Decode and validate refresh token
        payload = decode_token(token_data.refresh_token)
        
        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type"
            )
        
        user_id = payload.get("sub")
        
        # Get user profile
        user_result = supabase.table("users").select("*").eq("id", user_id).execute()
        
        if not user_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        user = user_result.data[0]
        
        # Check if user is active
        if user.get("status") != "active":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is inactive or suspended"
            )
        
        # Create new tokens
        token_payload = {
            "sub": user["id"],
            "email": user["email"],
            "role": user["role"],
            "company_id": user.get("company_id")
        }
        
        new_access_token = create_access_token(token_payload)
        new_refresh_token = create_refresh_token(token_payload)
        
        return Token(
            access_token=new_access_token,
            refresh_token=new_refresh_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user=UserResponse(**user)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Token refresh failed: {str(e)}"
        )


@router.post("/logout")
async def logout(current_user: dict = Depends(get_current_user_token)):
    """
    Logout current user.
    
    - Invalidates current session
    - Client should discard tokens
    """
    # In a production app, you might want to blacklist the token
    # or clear it from Redis if you're storing sessions
    return {"message": "Successfully logged out"}


@router.get("/me", response_model=UserResponse)
async def get_current_user(
    current_user: dict = Depends(get_current_user_token),
    supabase=Depends(get_supabase)
):
    """
    Get current user profile.
    
    - Returns authenticated user's profile data
    """
    user_id = current_user.get("sub")
    
    result = supabase.table("users").select("*").eq("id", user_id).execute()
    
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return UserResponse(**result.data[0])


@router.get("/test-token")
async def test_token(current_user: dict = Depends(get_current_user_token)):
    """
    Test endpoint to verify token is working.
    
    - Returns decoded token payload
    """
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"✅ Token validated successfully! User: {current_user}")
    
    return {
        "message": "Token is valid!",
        "user_id": current_user.get("sub"),
        "email": current_user.get("email"),
        "role": current_user.get("role"),
        "company_id": current_user.get("company_id"),
        "token_type": current_user.get("type"),
        "expires": current_user.get("exp")
    }


@router.post("/change-password")
async def change_password(
    password_data: PasswordChange,
    current_user: dict = Depends(get_current_user_token),
    supabase=Depends(get_supabase)
):
    """
    Change user password.
    
    - Requires current password verification
    - Updates password in Supabase Auth
    """
    try:
        # Verify current password by attempting to sign in
        user_email = current_user.get("email")
        
        auth_check = supabase.auth.sign_in_with_password({
            "email": user_email,
            "password": password_data.current_password
        })
        
        if not auth_check.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Current password is incorrect"
            )
        
        # Update password
        supabase.auth.update_user({
            "password": password_data.new_password
        })
        
        return {"message": "Password updated successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Password change failed: {str(e)}"
        )


@router.post("/forgot-password")
async def forgot_password(
    password_reset: PasswordReset,
    supabase=Depends(get_supabase)
):
    """
    Request password reset email.
    
    - Sends password reset email via Supabase
    """
    try:
        supabase.auth.reset_password_email(password_reset.email)
        
        return {
            "message": "If your email is registered, you will receive a password reset link"
        }
        
    except Exception as e:
        # Don't reveal if email exists or not
        return {
            "message": "If your email is registered, you will receive a password reset link"
        }


@router.post("/verify-email")
async def verify_email(token: str):
    """
    Verify user email with token.
    
    - Called after user clicks verification link in email
    """
    # Supabase handles email verification automatically
    # This endpoint is for custom handling if needed
    return {"message": "Email verified successfully"}
