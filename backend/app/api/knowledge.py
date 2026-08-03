"""
Knowledge base API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks, Form
from typing import Optional
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.knowledge import DocumentResponse, DocumentUploadResponse
from app.services.knowledge_service import KnowledgeService
from app.utils.dependencies import get_current_user
from app.models.user import User
from app.core.response import ApiResponse
from app.core.exceptions import BaseAppException, ValidationError
from app.rag.loader import ALLOWED_UPLOAD_EXTS

router = APIRouter()


def _validate_file_ext(filename: str) -> str:
    """校验上传文件后缀并返回归一化扩展名(上传与重新入库两处共用)。"""
    file_ext = filename.split('.')[-1].lower() if '.' in filename else ""
    if file_ext not in ALLOWED_UPLOAD_EXTS:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_FILE_TYPE",
                "message": f"Allowed file types: {', '.join(ALLOWED_UPLOAD_EXTS)}",
            },
        )
    return file_ext


@router.post("/documents", response_model=ApiResponse[DocumentUploadResponse])
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Upload a document to the knowledge base
    Processing is done asynchronously in the background
    """
    # Validate file type
    file_ext = _validate_file_ext(file.filename)

    # Validate file size (10MB limit)
    file_size = 0
    content = await file.read()
    file_size = len(content)
    
    if file_size > 10 * 1024 * 1024:  # 10MB
        raise HTTPException(
            status_code=400,
            detail={"code": "FILE_TOO_LARGE", "message": "File size exceeds 10MB limit"}
        )
    
    try:
        # Create document record
        document = KnowledgeService.create_document_record(
            db=db,
            user_id=current_user.id,
            file_name=file.filename,
            file_type=file_ext,
            file_size=file_size
        )
        
        # Add background task for processing
        background_tasks.add_task(
            KnowledgeService.process_document,
            db=db,
            document_id=document.id,
            file_content=content
        )
        
        return ApiResponse.ok(
            data=DocumentUploadResponse(
                document_id=document.id,
                status="processing",
                message="Document uploaded and processing started"
            ),
            message="Document uploaded successfully"
        )
        
    except BaseAppException as e:
        raise HTTPException(status_code=e.status_code, detail={"code": e.code, "message": e.message})


@router.get("/documents", response_model=ApiResponse[list[DocumentResponse]])
async def get_documents(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all documents in the knowledge base"""
    try:
        documents = KnowledgeService.get_documents(db, current_user.id)
        return ApiResponse.ok(
            data=[DocumentResponse.model_validate(doc) for doc in documents]
        )
    except BaseAppException as e:
        raise HTTPException(status_code=e.status_code, detail={"code": e.code, "message": e.message})


@router.delete("/documents/{document_id}", response_model=ApiResponse)
async def delete_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a document from the knowledge base"""
    try:
        KnowledgeService.delete_document(db, document_id, current_user.id)
        return ApiResponse.ok(message="Document deleted successfully")
    except BaseAppException as e:
        raise HTTPException(status_code=e.status_code, detail={"code": e.code, "message": e.message})


@router.get("/documents/{document_id}", response_model=ApiResponse[DocumentResponse])
async def get_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a single knowledge-base document by ID"""
    try:
        document = KnowledgeService.get_document(db, document_id, current_user.id)
        return ApiResponse.ok(data=DocumentResponse.model_validate(document))
    except BaseAppException as e:
        raise HTTPException(status_code=e.status_code, detail={"code": e.code, "message": e.message})


@router.put("/documents/{document_id}", response_model=ApiResponse[DocumentResponse])
async def update_document(
    document_id: int,
    background_tasks: BackgroundTasks,
    name: Optional[str] = Form(None, max_length=255, description="New document name (optional)"),
    file: UploadFile = File(None, description="New file to re-ingest (optional)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update a knowledge-base document.

    - Provide ``name`` to rename the document.
    - Provide ``file`` to re-ingest a new file (the document is reset to
      ``processing`` and re-vectorized in the background, exactly like upload).
    - At least one of ``name`` / ``file`` must be supplied.
    """
    try:
        # Require at least one update field
        file_provided = file is not None and file.filename
        if name is None and not file_provided:
            raise ValidationError("Either 'name' or 'file' must be provided")

        document = KnowledgeService.get_document(db, document_id, current_user.id)

        # Rename
        if name is not None:
            document.name = name
            db.commit()

        # Re-ingest a new file
        if file_provided:
            file_ext = _validate_file_ext(file.filename)

            content = await file.read()
            if len(content) > 10 * 1024 * 1024:  # 10MB
                raise HTTPException(
                    status_code=400,
                    detail={"code": "FILE_TOO_LARGE", "message": "File size exceeds 10MB limit"}
                )

            document.size = len(content)
            document.file_type = file_ext
            document.status = "processing"
            db.commit()

            background_tasks.add_task(
                KnowledgeService.process_document,
                db=db,
                document_id=document.id,
                file_content=content
            )

        return ApiResponse.ok(
            data=DocumentResponse.model_validate(document),
            message="Document updated successfully"
        )
    except BaseAppException as e:
        raise HTTPException(status_code=e.status_code, detail={"code": e.code, "message": e.message})
