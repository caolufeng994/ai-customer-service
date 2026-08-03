"""
Knowledge base service
"""
from sqlalchemy.orm import Session
from typing import List, Optional
import os
import uuid
from pathlib import Path
from app.models.kb_document import KbDocument
from app.models.kb_chunk import KbChunk
from app.config import settings
from app.schemas.knowledge import DocumentResponse
from app.rag.loader import DocumentLoader
from app.rag.splitter import TextSplitter
from app.rag.embedder import Embedder
from app.rag.vector_store import VectorStore
from app.core.exceptions import DocumentProcessingError, NotFoundError
import logging

logger = logging.getLogger(__name__)


class KnowledgeService:
    """Knowledge base business logic"""
    
    @staticmethod
    def create_document_record(
        db: Session,
        user_id: int,
        file_name: str,
        file_type: str,
        file_size: int,
        kb_id: str = "default"
    ) -> KbDocument:
        """Create a document record in processing state"""
        # Generate unique file path
        upload_dir = Path(settings.upload_dir)
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        file_ext = file_type
        unique_filename = f"{uuid.uuid4()}.{file_ext}"
        file_path = str(upload_dir / unique_filename)
        
        document = KbDocument(
            kb_id=kb_id,
            user_id=user_id,
            name=file_name,
            file_path=file_path,
            file_type=file_type,
            size=file_size,
            status="processing"
        )
        
        db.add(document)
        db.commit()
        db.refresh(document)
        
        return document
    
    @staticmethod
    def process_document(
        db: Session,
        document_id: int,
        file_content: bytes
    ) -> None:
        """
        Process document in background task
        This is the main pipeline: load -> split -> embed -> store
        """
        document = db.query(KbDocument).filter(KbDocument.id == document_id).first()
        if not document:
            logger.error(f"Document {document_id} not found")
            return
        
        try:
            # Save file content
            with open(document.file_path, 'wb') as f:
                f.write(file_content)
            
            # Step 1: Load document
            loader = DocumentLoader()
            text = loader.load(document.file_path, document.file_type)
            char_count = loader.get_char_count(text)
            
            # Step 2: Split text
            splitter = TextSplitter(chunk_size=500, chunk_overlap=80)
            chunks = splitter.split_text(text)
            
            # Step 3: Embed chunks
            embedder = Embedder()
            embeddings = embedder.embed_batch(chunks, batch_size=16)
            
            # Step 4: Store in vector database
            vector_store = VectorStore()
            
            # Prepare metadata and IDs
            chunk_ids = []
            metadatas = []
            
            for i, chunk in enumerate(chunks):
                chunk_id = f"doc_{document.id}_chunk_{i}"
                chunk_ids.append(chunk_id)
                metadatas.append({
                    "doc_id": document.id,
                    "kb_id": document.kb_id,
                    "doc_name": document.name,
                    "chunk_index": i
                })
            
            # Add to vector store
            vector_store.add_embeddings(
                embeddings=embeddings,
                texts=chunks,
                metadatas=metadatas,
                ids=chunk_ids
            )
            
            # Step 5: Save chunks to database
            for i, (chunk, chunk_id, embedding) in enumerate(zip(chunks, chunk_ids, embeddings)):
                kb_chunk = KbChunk(
                    doc_id=document.id,
                    chunk_index=i,
                    content=chunk,
                    char_count=len(chunk),
                    vector_id=chunk_id
                )
                db.add(kb_chunk)
            
            # Update document status
            document.char_count = char_count
            document.chunk_count = len(chunks)
            document.status = "ready"
            
            db.commit()
            logger.info(f"Successfully processed document {document_id}: {len(chunks)} chunks")
            
        except Exception as e:
            logger.error(f"Failed to process document {document_id}: {e}")
            document.status = "failed"
            document.error_msg = str(e)
            db.commit()
    
    @staticmethod
    def get_documents(db: Session, user_id: int, kb_id: str = "default") -> List[KbDocument]:
        """Get documents owned by the given user (per-user KB isolation)."""
        documents = db.query(KbDocument).filter(
            KbDocument.kb_id == kb_id,
            KbDocument.user_id == user_id
        ).order_by(KbDocument.created_at.desc()).all()
        return documents
    
    @staticmethod
    def get_document(db: Session, document_id: int, user_id: Optional[int] = None) -> KbDocument:
        """Get a specific document.

        When ``user_id`` is provided the lookup is scoped to that owner, so a
        user can only fetch their own documents (per-user KB isolation). When
        omitted (e.g. internal callers such as the background processor) the
        lookup is unscoped.
        """
        query = db.query(KbDocument).filter(KbDocument.id == document_id)
        if user_id is not None:
            query = query.filter(KbDocument.user_id == user_id)
        document = query.first()
        if not document:
            raise NotFoundError("Document not found")
        return document

    @staticmethod
    def delete_document(db: Session, document_id: int, user_id: Optional[int] = None) -> None:
        """
        Delete document and cascade delete vectors
        This ensures consistency between MySQL and Chroma.

        When ``user_id`` is provided the document must be owned by that user;
        otherwise a NotFoundError is raised (per-user KB isolation).
        """
        document = KnowledgeService.get_document(db, document_id, user_id)
        
        try:
            # Step 1: Update status to deleting
            document.status = "deleting"
            db.commit()
            
            # Step 2: Get all chunk vector IDs
            chunks = db.query(KbChunk).filter(KbChunk.doc_id == document_id).all()
            vector_ids = [chunk.vector_id for chunk in chunks]
            
            # Step 3: Delete from vector store
            if vector_ids:
                vector_store = VectorStore()
                vector_store.delete_by_ids(vector_ids)
            
            # Step 4: Delete chunks from database (cascade will handle this)
            # Step 5: Delete document from database
            db.delete(document)
            db.commit()
            
            # Step 6: Delete file from disk
            if os.path.exists(document.file_path):
                os.remove(document.file_path)
            
            logger.info(f"Successfully deleted document {document_id}")
            
        except Exception as e:
            logger.error(f"Failed to delete document {document_id}: {e}")
            document.status = "ready"  # Revert status on failure
            db.commit()
            raise DocumentProcessingError(f"Failed to delete document: {str(e)}")
