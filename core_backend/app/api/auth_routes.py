from fastapi import APIRouter, HTTPException, Body, Depends, status
from fastapi.security import OAuth2PasswordBearer
from app.middleware.auth import create_access_token, create_refresh_token, verify_jwt_token, blacklist_token, verify_password
from app.utils import db
from sqlalchemy import text
from pydantic import BaseModel, Field
import jwt
import logging
from typing import Dict, Any
from app.schemas.api_response import APIResponse

logger = logging.getLogger("auth_routes")

router = APIRouter(prefix="/auth", tags=["auth"])

# OAuth2 scheme for Swagger UI and dependency injection
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

class LoginRequest(BaseModel):
    user_id: str = Field(..., description="User unique identifier")
    password: str | None = Field(None, description="User password (required if not guest)")

class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., description="The refresh token provided during login")

class TokenResponse(BaseModel):
    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="JWT refresh token")
    token_type: str = Field(default="bearer", description="Token type")

class MessageResponse(BaseModel):
    message: str = Field(..., description="Status message")

class UserMeResponse(BaseModel):
    user_id: str = Field(..., description="The unique identifier of the user")
    type: str = Field(..., description="Token type (access/refresh)")

class ExchangeTokenRequest(BaseModel):
    visitor_id: str = Field(..., description="The unique ID of the visitor on the partner website")
    metadata: Dict[str, Any] | None = Field(default=None, description="Optional metadata about the visitor")

class ExchangeTokenResponse(BaseModel):
    access_token: str = Field(..., description="JWT access token for the visitor")
    refresh_token: str = Field(..., description="JWT refresh token for the visitor")
    visitor_id: str = Field(..., description="The ID assigned to the visitor")

@router.post("/exchange-token", response_model=APIResponse[ExchangeTokenResponse])
async def exchange_token(
    req: ExchangeTokenRequest = Body(...),
    partner_id: str = Depends(oauth2_scheme)
):
    """
    Server-to-Server Token Exchange.
    
    A partner website (authenticated via their own token) calls this to get 
     a scoped JWT for one of their visitors.
    """
    if not partner_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        # Validate the partner's token first
        payload = await verify_jwt_token(partner_id)
        authenticated_partner_id = payload.get("sub")
        
        # Create a scoped visitor ID to prevent collision across partners
        # Format: partner:visitor
        scoped_visitor_id = f"{authenticated_partner_id}:{req.visitor_id}"
        
        # Sign new tokens for the visitor using RS256
        # We now provide a refresh token for visitors so the widget can self-sustain
        # for the duration of the refresh TTL (7 days) without parent assistance.
        visitor_token = create_access_token({
            "sub": scoped_visitor_id,
            "partner": authenticated_partner_id,
            "metadata": req.metadata or {}
        })
        
        visitor_refresh_token = create_refresh_token({
            "sub": scoped_visitor_id,
            "partner": authenticated_partner_id,
            "type": "refresh"
        })
        
        return {
            "code": 200,
            "status": "success",
            "message": "Token exchange successful.",
            "data": {
                "access_token": visitor_token,
                "refresh_token": visitor_refresh_token,
                "visitor_id": scoped_visitor_id
            }
        }
    except Exception as e:
        logger.error(f"Token exchange failed: {str(e)}")
        raise HTTPException(status_code=401, detail="Invalid partner credentials or token")

@router.post("/login", response_model=APIResponse[TokenResponse], status_code=status.HTTP_200_OK)
async def login(req: LoginRequest = Body(...)):
    """
    Standard REST Login.
    
    Verifies credentials against the database if the user exists.
    Allows guest- prefix for development without passwords.
    """
    user_id = req.user_id
    pool = db.pool
    
    if not pool:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, 
            detail="Authentication service is currently unavailable (DB Down)"
        )

    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT password_hash FROM users WHERE user_id = %s", (user_id,))
            user = await cur.fetchone()
            
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED, 
                    detail="Invalid user_id or password"
                )
            
            # User exists, must verify password
            if not req.password:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, 
                    detail="Password is required"
                )
            
            if not verify_password(req.password, user[0]):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED, 
                    detail="Invalid user_id or password"
                )

    access_token = create_access_token({"sub": user_id})
    refresh_token = create_refresh_token({"sub": user_id})
    
    return {
        "code": 200,
        "status": "success",
        "message": "Login successful.",
        "data": {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer"
        }
    }

@router.post("/refresh", response_model=APIResponse[TokenResponse])
async def refresh(req: RefreshRequest = Body(...)):
    """
    Standard REST Token Refresh.
    
    Takes a refresh token and returns a new access token if valid.
    """
    try:
        payload = await verify_jwt_token(req.refresh_token)
        
        # Verify it's actually a refresh token
        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, 
                detail="Invalid token type: refresh token expected"
            )
            
        user_id = payload.get("sub")
        new_access_token = create_access_token({"sub": user_id})
        
        return {
            "code": 200,
            "status": "success",
            "message": "Token refreshed successfully.",
            "data": {
                "access_token": new_access_token,
                "refresh_token": req.refresh_token,
                "token_type": "bearer"
            }
        }
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Refresh token expired. Please login again."
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Invalid refresh token"
        )

@router.post("/logout", response_model=APIResponse[None])
async def logout(token: str = Depends(oauth2_scheme)):
    """
    Standard REST Logout.
    
    In a stateless JWT architecture, logout is primarily handled by the client 
    deleting the token. This endpoint adds the token to a Redis blacklist 
    to ensure it cannot be reused even if captured.
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    
    # Add token to Redis Blacklist
    await blacklist_token(token)
    
    return {
        "code": 200,
        "status": "success",
        "message": "Successfully logged out. Token has been invalidated."
    }

@router.get("/me", response_model=APIResponse[UserMeResponse])
async def get_current_user(token: str = Depends(oauth2_scheme)):
    """
    Standard REST GET /me.
    
    Validates the bearer token and returns the current user context.
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
        
    try:
        payload = await verify_jwt_token(token)
        return {
            "code": 200,
            "status": "success",
            "message": "User context retrieved.",
            "data": {
                "user_id": payload.get("sub"),
                "type": payload.get("type")
            }
        }
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired"
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials"
        )


