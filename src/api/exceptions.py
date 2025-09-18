"""
Custom exception classes for structured error handling.
"""

from fastapi import HTTPException, status
from typing import Optional, Any
import logging
from functools import wraps

logger = logging.getLogger(__name__)


class ChronosException(HTTPException):
    """Base exception for all Chronos-specific errors."""
    
    def __init__(
        self,
        status_code: int,
        detail: str,
        error_code: str = None,
        transaction_id: str = None
    ):
        super().__init__(status_code=status_code, detail=detail)
        self.error_code = error_code or self.__class__.__name__
        self.transaction_id = transaction_id


class ValidationError(ChronosException):
    """Raised when request validation fails."""
    
    def __init__(self, detail: str, field: str = None):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Validation error: {detail}" + (f" (field: {field})" if field else ""),
            error_code="VALIDATION_ERROR"
        )


class AuthenticationError(ChronosException):
    """Raised when authentication fails."""
    
    def __init__(self, detail: str = "Authentication required"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            error_code="AUTH_ERROR"
        )


class AuthorizationError(ChronosException):
    """Raised when user lacks required permissions."""
    
    def __init__(self, detail: str = "Insufficient permissions"):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
            error_code="AUTHZ_ERROR"
        )


class EventNotFoundError(ChronosException):
    """Raised when an event is not found."""
    
    def __init__(self, event_id: str):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Event with ID '{event_id}' not found",
            error_code="EVENT_NOT_FOUND"
        )


class CalendarSyncError(ChronosException):
    """Raised when Google Calendar sync fails."""
    
    def __init__(self, detail: str, transaction_id: str = None):
        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=detail,
            error_code="CALENDAR_SYNC_ERROR",
            transaction_id=transaction_id
        )


class DatabaseError(ChronosException):
    """Raised when database operations fail."""
    
    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {detail}",
            error_code="DATABASE_ERROR"
        )


def handle_api_errors(func):
    """
    Decorator to handle exceptions and convert them to appropriate HTTP responses.
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except ChronosException:
            # Re-raise our custom exceptions as-is
            raise
        except HTTPException:
            # Re-raise FastAPI exceptions as-is
            raise
        except ValueError as e:
            raise ValidationError(detail=str(e))
        except KeyError as e:
            raise ValidationError(detail=f"Missing required field: {str(e)}")
        except Exception as e:
            # Log unexpected errors
            logger.error(f"Unexpected error in {func.__name__}: {str(e)}", exc_info=True)
            raise ChronosException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An unexpected error occurred. Please try again later.",
                error_code="INTERNAL_ERROR"
            )
    
    return wrapper
