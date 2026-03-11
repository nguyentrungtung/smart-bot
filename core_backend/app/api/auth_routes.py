from fastapi import APIRouter, HTTPException, Body
from app.middleware.auth import create_access_token, create_refresh_token, verify_jwt_token
import jwt
from pydantic import BaseModel

router = APIRouter(prefix="/auth", tags=["auth"])

class LoginRequest(BaseModel):
    user_id: str = "test_user_123"

class RefreshRequest(BaseModel):
    refresh_token: str

@router.post("/login")
async def login(req: LoginRequest = Body(...)):
    """
    Mock login to facilitate obtaining tokens for testing.
    """
    user_id = req.user_id
    access_token = create_access_token({"sub": user_id})
    refresh_token = create_refresh_token({"sub": user_id})
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }

@router.post("/refresh")
async def refresh_token(req: RefreshRequest = Body(...)):
    """
    Takes a refresh token and returns a new access token if valid.
    """
    try:
        payload = verify_jwt_token(req.refresh_token)
        
        # Verify it's actually a refresh token
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=403, detail="Invalid token type")
            
        user_id = payload.get("sub")
        new_access_token = create_access_token({"sub": user_id})
        
        return {
            "access_token": new_access_token,
            "token_type": "bearer"
        }
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Refresh token expired. Please login again.")
    except jwt.PyJWTError:
        raise HTTPException(status_code=403, detail="Invalid refresh token")
