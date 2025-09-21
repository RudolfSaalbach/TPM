"""
Unified API Pagination and Filtering Standards
Provides consistent pagination, filtering, and sorting across all endpoints
"""

from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional, List, Generic, TypeVar
from pydantic import BaseModel, Field, validator
from fastapi import Query
from sqlalchemy import Select, func, asc, desc


T = TypeVar('T')


class SortOrder(str, Enum):
    """Standard sort order options"""
    ASC = "asc"
    DESC = "desc"


class FilterOperator(str, Enum):
    """Standard filter operators"""
    EQ = "eq"           # equals
    NE = "ne"           # not equals
    GT = "gt"           # greater than
    GTE = "gte"         # greater than or equal
    LT = "lt"           # less than
    LTE = "lte"         # less than or equal
    LIKE = "like"       # contains (case insensitive)
    IN = "in"           # in list
    IS_NULL = "is_null" # is null/empty
    IS_NOT_NULL = "is_not_null" # is not null/empty


class PaginationParams(BaseModel):
    """Standardized pagination parameters"""
    page: int = Field(1, ge=1, description="Page number (1-indexed)")
    page_size: int = Field(50, ge=1, le=1000, description="Items per page")

    @property
    def offset(self) -> int:
        """Calculate offset for database queries"""
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        """Get limit for database queries"""
        return self.page_size


class SortParams(BaseModel):
    """Standardized sorting parameters"""
    sort_by: Optional[str] = Field(None, description="Field to sort by")
    sort_order: SortOrder = Field(SortOrder.ASC, description="Sort order")

    def to_sql_order(self, column):
        """Convert to SQLAlchemy order clause"""
        if self.sort_order == SortOrder.DESC:
            return desc(column)
        return asc(column)


class FilterParam(BaseModel):
    """Individual filter parameter"""
    field: str = Field(..., description="Field name to filter on")
    operator: FilterOperator = Field(FilterOperator.EQ, description="Filter operator")
    value: Any = Field(..., description="Filter value")


class FilterParams(BaseModel):
    """Collection of filter parameters"""
    filters: List[FilterParam] = Field(default_factory=list, description="List of filters to apply")

    @classmethod
    def from_query_string(cls, filter_str: Optional[str]) -> 'FilterParams':
        """Parse filter string in format: field:operator:value,field2:operator2:value2"""
        if not filter_str:
            return cls()

        filters = []
        for filter_part in filter_str.split(','):
            parts = filter_part.strip().split(':')
            if len(parts) >= 2:
                field = parts[0]
                operator = FilterOperator(parts[1]) if len(parts) > 2 else FilterOperator.EQ
                value = ':'.join(parts[2:]) if len(parts) > 2 else parts[1]
                filters.append(FilterParam(field=field, operator=operator, value=value))

        return cls(filters=filters)


class SearchParams(BaseModel):
    """Standardized search parameters"""
    q: Optional[str] = Field(None, description="Search query string")
    search_fields: List[str] = Field(default_factory=list, description="Fields to search in")


class PaginationMeta(BaseModel):
    """Pagination metadata for responses"""
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Items per page")
    total_items: int = Field(..., description="Total number of items")
    total_pages: int = Field(..., description="Total number of pages")
    has_next: bool = Field(..., description="Whether there is a next page")
    has_prev: bool = Field(..., description="Whether there is a previous page")

    @classmethod
    def from_params(cls, params: PaginationParams, total_items: int) -> 'PaginationMeta':
        """Create pagination metadata from parameters and total count"""
        total_pages = (total_items + params.page_size - 1) // params.page_size
        return cls(
            page=params.page,
            page_size=params.page_size,
            total_items=total_items,
            total_pages=total_pages,
            has_next=params.page < total_pages,
            has_prev=params.page > 1
        )


class PaginatedResponse(BaseModel, Generic[T]):
    """Standardized paginated response"""
    success: bool = Field(True, description="Request success status")
    data: List[T] = Field(..., description="List of items")
    pagination: PaginationMeta = Field(..., description="Pagination metadata")
    filters_applied: Dict[str, Any] = Field(default_factory=dict, description="Applied filters")
    search_query: Optional[str] = Field(None, description="Applied search query")
    sort_applied: Optional[Dict[str, str]] = Field(None, description="Applied sorting")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Response timestamp")


class QueryBuilder:
    """Helper class to build standardized database queries"""

    def __init__(self, base_query: Select):
        self.query = base_query
        self.applied_filters = {}
        self.applied_search = None
        self.applied_sort = None

    def apply_pagination(self, params: PaginationParams) -> 'QueryBuilder':
        """Apply pagination to query"""
        self.query = self.query.offset(params.offset).limit(params.limit)
        return self

    def apply_filters(self, filters: FilterParams, column_mapping: Dict[str, Any]) -> 'QueryBuilder':
        """Apply filters to query"""
        for filter_param in filters.filters:
            if filter_param.field not in column_mapping:
                continue

            column = column_mapping[filter_param.field]
            value = filter_param.value

            if filter_param.operator == FilterOperator.EQ:
                self.query = self.query.where(column == value)
            elif filter_param.operator == FilterOperator.NE:
                self.query = self.query.where(column != value)
            elif filter_param.operator == FilterOperator.GT:
                self.query = self.query.where(column > value)
            elif filter_param.operator == FilterOperator.GTE:
                self.query = self.query.where(column >= value)
            elif filter_param.operator == FilterOperator.LT:
                self.query = self.query.where(column < value)
            elif filter_param.operator == FilterOperator.LTE:
                self.query = self.query.where(column <= value)
            elif filter_param.operator == FilterOperator.LIKE:
                self.query = self.query.where(column.ilike(f"%{value}%"))
            elif filter_param.operator == FilterOperator.IN:
                values = value.split(',') if isinstance(value, str) else value
                self.query = self.query.where(column.in_(values))
            elif filter_param.operator == FilterOperator.IS_NULL:
                self.query = self.query.where(column.is_(None))
            elif filter_param.operator == FilterOperator.IS_NOT_NULL:
                self.query = self.query.where(column.is_not(None))

            self.applied_filters[filter_param.field] = {
                "operator": filter_param.operator.value,
                "value": value
            }

        return self

    def apply_search(self, search: SearchParams, column_mapping: Dict[str, Any]) -> 'QueryBuilder':
        """Apply search to query"""
        if not search.q:
            return self

        if not search.search_fields:
            # If no specific fields, search in all string columns
            search.search_fields = [field for field, col in column_mapping.items()
                                   if hasattr(col.type, 'python_type') and col.type.python_type == str]

        search_conditions = []
        for field in search.search_fields:
            if field in column_mapping:
                column = column_mapping[field]
                search_conditions.append(column.ilike(f"%{search.q}%"))

        if search_conditions:
            from sqlalchemy import or_
            self.query = self.query.where(or_(*search_conditions))
            self.applied_search = search.q

        return self

    def apply_sort(self, sort: SortParams, column_mapping: Dict[str, Any]) -> 'QueryBuilder':
        """Apply sorting to query"""
        if sort.sort_by and sort.sort_by in column_mapping:
            column = column_mapping[sort.sort_by]
            self.query = self.query.order_by(sort.to_sql_order(column))
            self.applied_sort = {
                "field": sort.sort_by,
                "order": sort.sort_order.value
            }
        return self

    def get_count_query(self) -> Select:
        """Get count query for pagination"""
        return self.query.with_only_columns(func.count()).order_by(None)


# FastAPI dependency functions for consistent parameter injection
def pagination_params(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=1000, description="Items per page")
) -> PaginationParams:
    """FastAPI dependency for pagination parameters"""
    return PaginationParams(page=page, page_size=page_size)


def sort_params(
    sort_by: Optional[str] = Query(None, description="Field to sort by"),
    sort_order: SortOrder = Query(SortOrder.ASC, description="Sort order")
) -> SortParams:
    """FastAPI dependency for sort parameters"""
    return SortParams(sort_by=sort_by, sort_order=sort_order)


def filter_params(
    filters: Optional[str] = Query(None, description="Filters in format: field:operator:value,field2:operator2:value2")
) -> FilterParams:
    """FastAPI dependency for filter parameters"""
    return FilterParams.from_query_string(filters)


def search_params(
    q: Optional[str] = Query(None, description="Search query string")
) -> SearchParams:
    """FastAPI dependency for search parameters"""
    return SearchParams(q=q)


# Legacy parameter mapping for backward compatibility
def map_legacy_pagination(
    limit: Optional[int] = None,
    offset: Optional[int] = None,
    page: Optional[int] = None,
    page_size: Optional[int] = None
) -> PaginationParams:
    """Map legacy pagination parameters to new format"""

    # Use new parameters if provided
    if page is not None and page_size is not None:
        return PaginationParams(page=page, page_size=page_size)

    # Map legacy parameters
    if limit is not None and offset is not None:
        calculated_page = (offset // limit) + 1 if limit > 0 else 1
        return PaginationParams(page=calculated_page, page_size=limit)

    # Fallback to defaults
    return PaginationParams()


# Utility functions for response building
def build_paginated_response(
    data: List[T],
    pagination: PaginationParams,
    total_items: int,
    filters_applied: Optional[Dict[str, Any]] = None,
    search_query: Optional[str] = None,
    sort_applied: Optional[Dict[str, str]] = None
) -> PaginatedResponse[T]:
    """Build standardized paginated response"""
    pagination_meta = PaginationMeta.from_params(pagination, total_items)

    return PaginatedResponse(
        data=data,
        pagination=pagination_meta,
        filters_applied=filters_applied or {},
        search_query=search_query,
        sort_applied=sort_applied
    )