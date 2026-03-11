from pydantic import BaseModel, Field, validator
from typing import List, Optional, Any, Dict
import base64

class MessageAttachment(BaseModel):
    type: str = Field(..., description="Type of attachment: 'image' or 'audio'")
    data: str = Field(..., description="Base64 encoded data or URL")
    mime_type: Optional[str] = None

class MessageIn(BaseModel):
    session_id: str
    content: Optional[str] = ""
    attachments: Optional[List[MessageAttachment]] = []

    @validator('attachments')
    def validate_attachments(cls, v):
        for attachment in v:
            if attachment.type not in ["image", "audio"]:
                raise ValueError("Attachment type must be 'image' or 'audio'")
            
            # Strict MIME validation
            allowed_mimes = ["image/png", "image/jpeg", "audio/webm"]
            if attachment.mime_type and attachment.mime_type not in allowed_mimes:
                raise ValueError(f"MIME type {attachment.mime_type} not supported. Use PNG, JPEG, or WebM.")
            
            # Approx 5MB check for base64 (5 * 1024 * 1024 * 1.33)
            if len(attachment.data) > 7000000:
                raise ValueError("Attachment too large (> 5MB)")
        return v


class ChatUpdate(BaseModel):
    session_id: str
    sender: str  # 'bot' or 'user'
    content: str
    type: str = "text"  # 'text', 'image', 'audio'
    thought: Optional[str] = None

class ThinkingUpdate(BaseModel):
    session_id: str
    content: str  # The thought chunk
