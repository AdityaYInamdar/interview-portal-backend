"""
Security utilities for authentication and authorization.
"""
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from jose import jwt, JWTError
from passlib.context import CryptContext
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.core.config import settings

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# HTTP Bearer token security
security = HTTPBearer()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a hashed password."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password."""
    return pwd_context.hash(password)


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token.
    
    Args:
        data: Data to encode in the token
        expires_delta: Token expiration time
        
    Returns:
        Encoded JWT token
    """
    import logging
    logger = logging.getLogger(__name__)
    
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire, "type": "access"})
    
    logger.info(f"Creating access token with data: {data}")
    logger.info(f"Token will expire at: {expire}")
    logger.info(f"Using SECRET_KEY (first 10 chars): {settings.SECRET_KEY[:10]}...")
    
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    
    logger.info(f"Access token created. Length: {len(encoded_jwt)}, First 30 chars: {encoded_jwt[:30]}...")
    
    return encoded_jwt


def create_refresh_token(data: Dict[str, Any]) -> str:
    """
    Create a JWT refresh token.
    
    Args:
        data: Data to encode in the token
        
    Returns:
        Encoded JWT token
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def decode_token(token: str) -> Dict[str, Any]:
    """
    Decode and verify a JWT token.
    
    Args:
        token: JWT token to decode
        
    Returns:
        Decoded token payload
        
    Raises:
        HTTPException: If token is invalid or expired
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        logger.info(f"Attempting to decode token. Token length: {len(token)}, First 30 chars: {token[:30]}...")
        logger.info(f"Using SECRET_KEY (first 10 chars): {settings.SECRET_KEY[:10]}...")
        logger.info(f"Using ALGORITHM: {settings.ALGORITHM}")
        
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        logger.info(f"Token decoded successfully. Payload: {payload}")
        return payload
    except JWTError as e:
        logger.error(f"JWT decode error: {type(e).__name__} - {str(e)}")
        logger.error(f"Token that failed: {token[:50]}...")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, Any]:
    """
    Dependency to get the current user from the access token.
    
    Args:
        credentials: HTTP Bearer credentials
        
    Returns:
        Decoded token payload
    """
    token = credentials.credentials
    
    # Add logging for debugging
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Attempting to validate token: {token[:20]}...")
    
    try:
        payload = decode_token(token)
        logger.info(f"Token decoded successfully for user: {payload.get('sub')}")
    except HTTPException as e:
        logger.error(f"Token validation failed: {e.detail}")
        raise
    
    # Verify it's an access token
    if payload.get("type") != "access":
        logger.error(f"Invalid token type: {payload.get('type')}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type"
        )
    
    # Check if token has expired
    exp = payload.get("exp")
    if exp is None:
        logger.error("Token missing expiration")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing expiration"
        )
    
    exp_datetime = datetime.fromtimestamp(exp)
    if exp_datetime < datetime.utcnow():
        logger.error(f"Token expired at {exp_datetime}, current time: {datetime.utcnow()}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired"
        )
    
    logger.info(f"Token validated successfully. Expires at: {exp_datetime}")
    return payload


def verify_user_role(required_roles: list):
    """
    Dependency factory to verify user has required role.
    
    Args:
        required_roles: List of roles that are allowed
        
    Returns:
        Dependency function
    """
    async def role_checker(current_user: Dict = Depends(get_current_user_token)) -> Dict:
        user_role = current_user.get("role")
        if user_role not in required_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required roles: {required_roles}"
            )
        return current_user
    
    return role_checker


# Role-based dependencies
require_admin = verify_user_role(["admin"])
require_interviewer = verify_user_role(["admin", "interviewer"])
require_any_user = verify_user_role(["admin", "interviewer", "candidate"])


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, Any]:
    """
    Dependency to get current user with proper field mapping.
    Maps 'sub' to 'id' for easier usage in API endpoints.
    
    Returns:
        Dict with user data: {id, email, role, company_id}
    """
    token_payload = await get_current_user_token(credentials)
    
    # Map token fields to user fields for convenience
    user_data = {
        'id': token_payload.get('sub'),  # Map 'sub' to 'id'
        'email': token_payload.get('email'),
        'role': token_payload.get('role'),
        'company_id': token_payload.get('company_id'),
    }
    
    return user_data


def require_role(allowed_roles: list):
    """
    Dependency factory to require specific roles.
    
    Args:
        allowed_roles: List of allowed roles (e.g., ["admin", "interviewer"])
        
    Returns:
        Dependency function that validates user role
        
    Example:
        @router.get("/admin-only")
        async def admin_route(current_user: dict = Depends(require_role(["admin"]))):
            ...
    """
    async def role_checker(current_user: Dict = Depends(get_current_user)) -> Dict:
        user_role = current_user.get("role")
        if user_role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required roles: {allowed_roles}"
            )
        return current_user
    
    return role_checker
