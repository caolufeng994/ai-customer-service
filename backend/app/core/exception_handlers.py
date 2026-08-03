"""
Global Exception Handlers
Converts exceptions to standardized API responses.

Error-response contract (consistent across the whole API):
  * 2xx  -> ApiResponse envelope  {success, code:"SUCCESS", message, data}
  * 4xx/5xx -> {detail: {code, message}}   (uniform with the HTTPException
            detail shape already produced by every endpoint)
  * 422  -> Pydantic validation array  [{loc, msg, type, ...}]  (standard)

Keeping the error shape uniform means clients can rely on `detail.code` /
`detail.message` for every non-422 failure, regardless of whether it was
raised as an HTTPException in a route, a BaseAppException that escaped a
try/except, or an unexpected server error.
"""
from fastapi import Request, status
from fastapi.responses import JSONResponse
from app.core.exceptions import BaseAppException
import logging

logger = logging.getLogger(__name__)


def _error_body(code: str, message: str) -> dict:
    """Build the uniform error envelope used by all non-422 failures."""
    return {"detail": {"code": code, "message": message}}


async def base_app_exception_handler(request: Request, exc: BaseAppException) -> JSONResponse:
    """Handle custom application exceptions (uniform {detail:{code,message}} shape)."""
    logger.error(f"Application error: {exc.code} - {exc.message}")
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_body(exc.code, exc.message),
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions with the same uniform error shape."""
    logger.exception(f"Unexpected error: {str(exc)}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_error_body("INTERNAL_ERROR", "An unexpected error occurred"),
    )
