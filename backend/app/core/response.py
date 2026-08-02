"""
Unified Response Wrapper
Standardizes API response format across all endpoints
"""
from typing import Any, Optional, Generic, TypeVar, List
from pydantic import BaseModel, Field

T = TypeVar('T')


class ApiResponse(BaseModel, Generic[T]):
    """Standard API response wrapper"""
    success: bool = Field(default=True, description="Request success status")
    code: str = Field(default="SUCCESS", description="Response code")
    message: str = Field(default="Operation successful", description="Response message")
    data: Optional[T] = Field(default=None, description="Response data")
    
    @classmethod
    def ok(cls, data: Any = None, message: str = "Operation successful") -> "ApiResponse[T]":
        """Create success response"""
        return cls(success=True, code="SUCCESS", message=message, data=data)
    
    @classmethod
    def error(cls, code: str, message: str, data: Any = None) -> "ApiResponse[T]":
        """Create error response"""
        return cls(success=False, code=code, message=message, data=data)


class PaginationMeta(BaseModel):
    """Pagination metadata"""
    total: int = Field(description="Total number of items")
    page: int = Field(description="Current page number (1-indexed)")
    page_size: int = Field(description="Number of items per page")
    total_pages: int = Field(description="Total number of pages")


class PaginatedResponse(ApiResponse[T]):
    """Paginated API response"""
    data: Optional[List[T]] = Field(default=None, description="Response data list")
    meta: Optional[PaginationMeta] = Field(default=None, description="Pagination metadata")
    
    @classmethod
    def ok(
        cls,
        data: Any,
        total: int,
        page: int = 1,
        page_size: int = 20,
        message: str = "Operation successful"
    ) -> "PaginatedResponse[T]":
        """Create paginated success response"""
        total_pages = (total + page_size - 1) // page_size if total > 0 else 0
        meta = PaginationMeta(
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages
        )
        return cls(success=True, code="SUCCESS", message=message, data=data, meta=meta)
