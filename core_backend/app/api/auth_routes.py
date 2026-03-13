from fastapi import APIRouter, HTTPException, Body, Depends, status
from fastapi.security import OAuth2PasswordBearer
from app.middleware.auth import create_access_token, create_refresh_token, verify_jwt_token, blacklist_token
from pydantic import BaseModel, Field
import jwt
from typing import Dict, Any

router = APIRouter(prefix="/auth", tags=["auth"])

# OAuth2 scheme for Swagger UI and dependency injection
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login", auto_error=False)

class LoginRequest(BaseModel):
    user_id: str = Field(default="test_user_123", description="User identifier for login")

class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., description="The refresh token provided during login")

class TokenResponse(BaseModel):
    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="JWT refresh token")
    token_type: str = Field(default="bearer", description="Token type")

class MessageResponse(BaseModel):
    detail: str = Field(..., description="Status message")

class UserMeResponse(BaseModel):
    user_id: str = Field(..., description="The unique identifier of the user")
    type: str = Field(..., description="Token type (access/refresh)")

@router.post("/login", response_model=TokenResponse, status_code=status.HTTP_200_OK)
async def login(req: LoginRequest = Body(...)):
    """
    Standard REST Login.
    
    Mocks authentication to facilitate obtaining RS256 tokens for testing.
    In production, this would verify credentials against a database.
    """
    user_id = req.user_id
    
    access_token = create_access_token({"sub": user_id})
    refresh_token = create_refresh_token({"sub": user_id})
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }

@router.post("/refresh", response_model=TokenResponse)
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
            "access_token": new_access_token,
            "refresh_token": req.refresh_token, # Reuse the same refresh token
            "token_type": "bearer"
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

@router.post("/logout", response_model=MessageResponse)
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
    
    return {"detail": "Successfully logged out. Token has been invalidated."}

@router.get("/me", response_model=UserMeResponse)
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
            "user_id": payload.get("sub"),
            "type": payload.get("type")
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


