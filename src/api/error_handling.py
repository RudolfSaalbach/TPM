"""
Centralized API Error Handling
Provides consistent error responses and exception handling
"""

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from typing import Dict, Any, Optional, List
import logging
import uuid
import json
from datetime import datetime

from .standard_schemas import (
    ErrorCode, APIErrorResponse, APIErrorDetail,
    create_error_response
)

logger = logging.getLogger(__name__)


class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles datetime objects"""
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


def safe_json_response(content: Dict[str, Any], status_code: int = 200) -> JSONResponse:
    """Create JSONResponse with datetime-safe serialization"""
    json_content = json.loads(json.dumps(content, cls=DateTimeEncoder))
    return JSONResponse(status_code=status_code, content=json_content)


class APIError(Exception):
    """Enhanced API error with standardized error codes"""

    def __init__(
        self,
        message: str,
        error_code: ErrorCode = ErrorCode.INTERNAL_ERROR,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: Optional[List[APIErrorDetail]] = None,
        request_id: Optional[str] = None
    ):
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.details = details or []
        self.request_id = request_id or str(uuid.uuid4())
        super().__init__(message)


class ValidationAPIError(APIError):
    """Validation-specific API error"""

    def __init__(
        self,
        message: str,
        field_errors: List[APIErrorDetail],
        request_id: Optional[str] = None
    ):
        super().__init__(
            message=message,
            error_code=ErrorCode.VALIDATION_ERROR,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=field_errors,
            request_id=request_id
        )


class NotFoundAPIError(APIError):
    """Resource not found API error"""

    def __init__(self, resource: str, identifier: str, request_id: Optional[str] = None):
        super().__init__(
            message=f"{resource} with identifier '{identifier}' not found",
            error_code=ErrorCode.NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            request_id=request_id
        )


class ConflictAPIError(APIError):
    """Resource conflict API error"""

    def __init__(self, message: str, request_id: Optional[str] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.CONFLICT,
            status_code=status.HTTP_409_CONFLICT,
            request_id=request_id
        )


class UnauthorizedAPIError(APIError):
    """Authentication/authorization API error"""

    def __init__(
        self,
        message: str = "Authentication required",
        error_code: ErrorCode = ErrorCode.UNAUTHORIZED,
        request_id: Optional[str] = None
    ):
        super().__init__(
            message=message,
            error_code=error_code,
            status_code=status.HTTP_401_UNAUTHORIZED,
            request_id=request_id
        )


def create_error_response(
    message: str,
    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
    error_code: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None
) -> JSONResponse:
    """Create standardized error response"""
    error_payload = {
        "detail": message,
        "status_code": status_code
    }

    if error_code:
        error_payload["error_code"] = error_code

    if details:
        error_payload["details"] = details

    return JSONResponse(
        status_code=status_code,
        content=error_payload
    )


async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    """Enhanced global exception handler for APIError"""
    logger.error(
        f"API Error: {exc.message} (code: {exc.error_code.value}, request_id: {exc.request_id})",
        extra={"request_id": exc.request_id, "error_code": exc.error_code.value}
    )

    error_response = APIErrorResponse(
        error=exc.message,
        error_code=exc.error_code,
        details=exc.details,
        request_id=exc.request_id
    )

    return safe_json_response(
        content=error_response.dict(),
        status_code=exc.status_code
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Enhanced HTTP exception handler with standardized format"""
    request_id = str(uuid.uuid4())

    # Map HTTP status codes to error codes
    error_code_mapping = {
        400: ErrorCode.VALIDATION_ERROR,
        401: ErrorCode.UNAUTHORIZED,
        403: ErrorCode.FORBIDDEN,
        404: ErrorCode.NOT_FOUND,
        409: ErrorCode.CONFLICT,
        422: ErrorCode.VALIDATION_ERROR,
        500: ErrorCode.INTERNAL_ERROR
    }

    error_code = error_code_mapping.get(exc.status_code, ErrorCode.INTERNAL_ERROR)

    logger.error(
        f"HTTP Exception: {exc.detail} (status: {exc.status_code}, request_id: {request_id})",
        extra={"request_id": request_id, "status_code": exc.status_code}
    )

    error_response = APIErrorResponse(
        error=exc.detail,
        error_code=error_code,
        request_id=request_id
    )

    return safe_json_response(
        content=error_response.dict(),
        status_code=exc.status_code
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle Pydantic validation errors"""
    request_id = str(uuid.uuid4())

    # Convert Pydantic errors to our standard format
    field_errors = []
    for error in exc.errors():
        field_path = " -> ".join(str(loc) for loc in error["loc"])
        field_errors.append(
            APIErrorDetail(
                field=field_path,
                message=error["msg"],
                code=error["type"]
            )
        )

    logger.warning(
        f"Validation Error: {len(field_errors)} field errors (request_id: {request_id})",
        extra={"request_id": request_id, "errors": field_errors}
    )

    error_response = APIErrorResponse(
        error="Validation failed",
        error_code=ErrorCode.VALIDATION_ERROR,
        details=field_errors,
        request_id=request_id
    )

    return safe_json_response(
        content=error_response.dict(),
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
    )


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Enhanced catch-all exception handler"""
    request_id = str(uuid.uuid4())

    logger.error(
        f"Unhandled exception: {str(exc)} (request_id: {request_id})",
        exc_info=True,
        extra={"request_id": request_id, "exception_type": type(exc).__name__}
    )

    error_response = APIErrorResponse(
        error="Internal server error",
        error_code=ErrorCode.INTERNAL_ERROR,
        request_id=request_id
    )

    return safe_json_response(
        content=error_response.dict(),
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
    )


# Decorator for consistent error handling (backward compatibility)
def handle_api_errors(func):
    """Decorator for backward compatibility with existing error handling"""
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except HTTPException:
            raise  # Re-raise HTTP exceptions as-is
        except APIError:
            raise  # Re-raise API errors as-is
        except Exception as e:
            logger.error(f"Unexpected error in {func.__name__}: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Internal error: {str(e)}"
            )
    return wrapper