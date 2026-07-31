"""
Global Exception Handlers
Converts exceptions to standardized API responses
"""
from fastapi import Request, status
from fastapi.responses import JSONResponse
from app.core.exceptions import BaseAppException
from app.core.response import ApiResponse
import logging

logger = logging.getLogger(__name__)


async def base_app_exception_handler(request: Request, exc: BaseAppException) -> JSONResponse:
    """Handle custom application exceptions"""
    logger.error(f"Application error: {exc.code} - {exc.message}")
    
    return JSONResponse(
        status_code=exc.status_code,
        content=ApiResponse.error(
            code=exc.code,
            message=exc.message,
            data=exc.details
        ).model_dump()
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions"""
    logger.exception(f"Unexpected error: {str(exc)}")
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ApiResponse.error(
            code="INTERNAL_ERROR",
            message="An unexpected error occurred"
        ).model_dump()
    )
