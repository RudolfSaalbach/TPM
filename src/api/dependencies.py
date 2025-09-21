"""
API Dependencies for FastAPI Router Modules
Shared dependencies for authentication, scheduling, database access
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
import logging

from src.core.scheduler import ChronosScheduler
from src.core.database import db_service

# Initialize security scheme
security = HTTPBearer(auto_error=False)
logger = logging.getLogger(__name__)


class APIAuthenticator:
    """Centralized API authentication handler"""

    def __init__(self, api_key: str):
        self.api_key = api_key

    def verify_api_key(self, credentials: Optional[HTTPAuthorizationCredentials] = None) -> bool:
        """Verify API key from authorization header"""
        if not credentials:
            return False

        if credentials.credentials != self.api_key:
            return False

        return True

    def raise_unauthorized(self):
        """Raise unauthorized error"""
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )


# Global authenticator instance (will be set during app initialization)
_authenticator: Optional[APIAuthenticator] = None


def init_api_dependencies(api_key: str):
    """Initialize API dependencies with configuration"""
    global _authenticator
    _authenticator = APIAuthenticator(api_key)


async def verify_api_key(credentials: HTTPAuthorizationCredentials = Depends(security)) -> bool:
    """FastAPI dependency for API key verification"""
    if not _authenticator:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="API authentication not initialized"
        )

    if not credentials:
        _authenticator.raise_unauthorized()

    if not _authenticator.verify_api_key(credentials):
        _authenticator.raise_unauthorized()

    return True


async def get_scheduler() -> ChronosScheduler:
    """FastAPI dependency to get scheduler instance"""
    # This will be injected during router registration
    # For now, we'll access it from the global state
    # In a production app, this would come from dependency injection
    from src.main import get_scheduler_instance
    return get_scheduler_instance()


async def get_db_session():
    """FastAPI dependency to get database session"""
    async with db_service.get_session() as session:
        yield session


# Future: Scope-based authentication dependency
# async def require_scopes(required_scopes: List[str]):
#     """FastAPI dependency factory for scope-based authentication"""
#     async def check_scopes(
#         credentials: HTTPAuthorizationCredentials = Depends(security)
#     ) -> bool:
#         # Implementation for scope checking would go here
#         # This is a placeholder for Phase 4 of the refactoring
#         return await verify_api_key(credentials)
#     return check_scopes