from pydantic import BaseModel, Field
from typing import Any, Generic, TypeVar, Optional

T = TypeVar("T")

class APIResponse(BaseModel, Generic[T]):
    code: int = Field(200, description="The HTTP status code")
    status: str = Field("success", description="The status of the response (success/error)")
    message: Optional[str] = Field(None, description="Optional message describing the result")
    data: Optional[T] = Field(None, description="The actual data payload")

class ErrorResponse(BaseModel):
    code: int = Field(..., description="The HTTP status code")
    status: str = Field("error", description="Always 'error' for error responses")
    message: str = Field(..., description="The error message")
    errors: Optional[Any] = Field(None, description="Detailed error information (e.g., validation errors)")
