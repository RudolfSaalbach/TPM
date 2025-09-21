"""
API Deprecation Management System
Provides warnings and tracking for deprecated API features
"""

import logging
import warnings
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, Any, Optional, List, Set
from functools import wraps

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class DeprecationLevel(str, Enum):
    """Deprecation severity levels"""
    INFO = "info"           # Notice of future deprecation
    WARNING = "warning"     # Deprecated but still supported
    CRITICAL = "critical"   # Will be removed soon
    SUNSET = "sunset"       # Final warning before removal


class DeprecationNotice(BaseModel):
    """Structured deprecation notice"""
    feature: str = Field(..., description="The deprecated feature name")
    level: DeprecationLevel = Field(..., description="Deprecation severity")
    message: str = Field(..., description="Human-readable deprecation message")
    alternative: Optional[str] = Field(None, description="Recommended alternative")
    removal_date: Optional[str] = Field(None, description="Planned removal date (ISO format)")
    documentation_url: Optional[str] = Field(None, description="Migration guide URL")


class DeprecationTracker:
    """Global deprecation tracking and warning system"""

    def __init__(self):
        self._deprecations: Dict[str, DeprecationNotice] = {}
        self._usage_stats: Dict[str, int] = {}
        self._last_warnings: Dict[str, datetime] = {}
        self._warning_cooldown = timedelta(minutes=5)  # Limit log spam

    def register_deprecation(
        self,
        feature: str,
        level: DeprecationLevel,
        message: str,
        alternative: Optional[str] = None,
        removal_date: Optional[str] = None,
        documentation_url: Optional[str] = None
    ):
        """Register a deprecated feature"""
        self._deprecations[feature] = DeprecationNotice(
            feature=feature,
            level=level,
            message=message,
            alternative=alternative,
            removal_date=removal_date,
            documentation_url=documentation_url
        )
        logger.info(f"Registered deprecation: {feature} ({level.value})")

    def track_usage(self, feature: str, request_details: Optional[Dict[str, Any]] = None):
        """Track usage of deprecated feature"""
        if feature not in self._deprecations:
            return

        self._usage_stats[feature] = self._usage_stats.get(feature, 0) + 1

        # Rate-limited logging to prevent spam
        now = datetime.utcnow()
        last_warning = self._last_warnings.get(feature)

        if not last_warning or (now - last_warning) > self._warning_cooldown:
            deprecation = self._deprecations[feature]
            logger.warning(
                f"Deprecated feature used: {feature} ({deprecation.level.value}). "
                f"{deprecation.message}",
                extra={
                    "deprecated_feature": feature,
                    "deprecation_level": deprecation.level.value,
                    "usage_count": self._usage_stats[feature],
                    "request_details": request_details
                }
            )
            self._last_warnings[feature] = now

    def get_deprecation_notice(self, feature: str) -> Optional[DeprecationNotice]:
        """Get deprecation notice for a feature"""
        return self._deprecations.get(feature)

    def get_all_deprecations(self) -> Dict[str, DeprecationNotice]:
        """Get all registered deprecations"""
        return self._deprecations.copy()

    def get_usage_stats(self) -> Dict[str, int]:
        """Get usage statistics for deprecated features"""
        return self._usage_stats.copy()


# Global tracker instance
deprecation_tracker = DeprecationTracker()


def deprecate_parameter(
    parameter: str,
    level: DeprecationLevel = DeprecationLevel.WARNING,
    message: Optional[str] = None,
    alternative: Optional[str] = None,
    removal_date: Optional[str] = None
):
    """Decorator to mark API parameters as deprecated"""

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Check if deprecated parameter is being used
            if parameter in kwargs and kwargs[parameter] is not None:
                feature_name = f"parameter:{parameter}"

                # Register deprecation if not already registered
                if feature_name not in deprecation_tracker._deprecations:
                    default_message = message or f"Parameter '{parameter}' is deprecated"
                    deprecation_tracker.register_deprecation(
                        feature=feature_name,
                        level=level,
                        message=default_message,
                        alternative=alternative,
                        removal_date=removal_date
                    )

                # Track usage
                deprecation_tracker.track_usage(
                    feature_name,
                    {"function": func.__name__, "parameter": parameter, "value": str(kwargs[parameter])}
                )

            return await func(*args, **kwargs)
        return wrapper
    return decorator


def deprecate_endpoint(
    endpoint: str,
    level: DeprecationLevel = DeprecationLevel.WARNING,
    message: Optional[str] = None,
    alternative: Optional[str] = None,
    removal_date: Optional[str] = None
):
    """Decorator to mark entire API endpoints as deprecated"""

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            feature_name = f"endpoint:{endpoint}"

            # Register deprecation if not already registered
            if feature_name not in deprecation_tracker._deprecations:
                default_message = message or f"Endpoint '{endpoint}' is deprecated"
                deprecation_tracker.register_deprecation(
                    feature=feature_name,
                    level=level,
                    message=default_message,
                    alternative=alternative,
                    removal_date=removal_date
                )

            # Track usage
            deprecation_tracker.track_usage(
                feature_name,
                {"function": func.__name__, "endpoint": endpoint}
            )

            return await func(*args, **kwargs)
        return wrapper
    return decorator


def add_deprecation_headers(response: Response, deprecations: List[DeprecationNotice]):
    """Add deprecation headers to API response"""
    if not deprecations:
        return

    # Add standard deprecation header
    response.headers["Deprecation"] = "true"

    # Add custom headers with deprecation details
    for i, dep in enumerate(deprecations):
        prefix = f"X-API-Deprecation-{i + 1}"
        response.headers[f"{prefix}-Feature"] = dep.feature
        response.headers[f"{prefix}-Level"] = dep.level.value
        response.headers[f"{prefix}-Message"] = dep.message

        if dep.alternative:
            response.headers[f"{prefix}-Alternative"] = dep.alternative
        if dep.removal_date:
            response.headers[f"{prefix}-Removal-Date"] = dep.removal_date


def create_deprecation_middleware():
    """Create middleware to automatically add deprecation headers"""

    async def deprecation_middleware(request: Request, call_next):
        # Store deprecations found during request processing
        request.state.deprecations = []

        # Process request
        response = await call_next(request)

        # Add deprecation headers if any were tracked
        if hasattr(request.state, 'deprecations') and request.state.deprecations:
            add_deprecation_headers(response, request.state.deprecations)

        return response

    return deprecation_middleware


# Pre-register known legacy deprecations
def register_legacy_deprecations():
    """Register all known legacy API patterns for tracking"""

    # Legacy pagination parameters
    deprecation_tracker.register_deprecation(
        feature="parameter:limit",
        level=DeprecationLevel.WARNING,
        message="Parameter 'limit' is deprecated. Use 'page_size' instead.",
        alternative="page_size parameter with page-based pagination",
        removal_date="2024-06-01",
        documentation_url="/docs#pagination"
    )

    deprecation_tracker.register_deprecation(
        feature="parameter:offset",
        level=DeprecationLevel.WARNING,
        message="Parameter 'offset' is deprecated. Use 'page' instead.",
        alternative="page parameter with page-based pagination",
        removal_date="2024-06-01",
        documentation_url="/docs#pagination"
    )

    # Legacy filtering parameters
    deprecation_tracker.register_deprecation(
        feature="parameter:priority_filter",
        level=DeprecationLevel.WARNING,
        message="Parameter 'priority_filter' is deprecated. Use standardized filtering.",
        alternative="Use query parameter 'q' with priority:value syntax",
        removal_date="2024-06-01",
        documentation_url="/docs#filtering"
    )

    # Legacy response formats
    deprecation_tracker.register_deprecation(
        feature="response:raw_dict",
        level=DeprecationLevel.INFO,
        message="Raw dictionary responses are being standardized to structured schemas.",
        alternative="Use endpoints with response_model declarations",
        removal_date="2024-07-01",
        documentation_url="/docs#response-schemas"
    )


# Initialize legacy deprecations on module import
register_legacy_deprecations()