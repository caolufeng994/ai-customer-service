"""
Custom Exception Classes
"""
from typing import Optional, Any


class BaseAppException(Exception):
    """Base application exception"""
    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_ERROR",
        status_code: int = 500,
        details: Optional[Any] = None
    ):
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details
        super().__init__(self.message)


class ValidationError(BaseAppException):
    """Validation error"""
    def __init__(self, message: str, details: Optional[Any] = None):
        super().__init__(
            message=message,
            code="VALIDATION_ERROR",
            status_code=400,
            details=details
        )


class AuthenticationError(BaseAppException):
    """Authentication error"""
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(
            message=message,
            code="AUTH_ERROR",
            status_code=401
        )


class AuthorizationError(BaseAppException):
    """Authorization error"""
    def __init__(self, message: str = "Permission denied"):
        super().__init__(
            message=message,
            code="AUTHORIZATION_ERROR",
            status_code=403
        )


class NotFoundError(BaseAppException):
    """Resource not found error"""
    def __init__(self, message: str = "Resource not found"):
        super().__init__(
            message=message,
            code="NOT_FOUND",
            status_code=404
        )


class QuotaExceededError(BaseAppException):
    """Quota exceeded error"""
    def __init__(self, message: str = "Daily quota exceeded"):
        super().__init__(
            message=message,
            code="QUOTA_EXCEEDED",
            status_code=429
        )


class LLMError(BaseAppException):
    """LLM service error"""
    def __init__(self, message: str, details: Optional[Any] = None):
        super().__init__(
            message=message,
            code="LLM_ERROR",
            status_code=503,
            details=details
        )


class EmbeddingError(BaseAppException):
    """Embedding service error"""
    def __init__(self, message: str):
        super().__init__(
            message=message,
            code="EMBEDDING_ERROR",
            status_code=503
        )


class VectorStoreError(BaseAppException):
    """Vector store error"""
    def __init__(self, message: str):
        super().__init__(
            message=message,
            code="VECTOR_STORE_ERROR",
            status_code=503
        )


class DocumentProcessingError(BaseAppException):
    """Document processing error"""
    def __init__(self, message: str, details: Optional[Any] = None):
        super().__init__(
            message=message,
            code="DOC_PROCESSING_ERROR",
            status_code=500,
            details=details
        )
