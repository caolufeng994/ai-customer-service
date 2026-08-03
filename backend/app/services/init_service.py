"""
Knowledge base seeding / initialization service.

Reads the pre-packaged seed documents under <project_root>/seed_docs and runs
them through the standard RAG ingestion pipeline
(loader -> splitter -> embedder -> vector_store) so the knowledge base is
populated and the full RAG chain is testable immediately after startup.

Idempotent by design: a seed document that is already ingested
(status == "ready") is skipped unless force=True. This makes it safe to run the
CLI repeatedly and safe to enable auto-initialization on every server start.
"""
from pathlib import Path
from typing import Dict, Any
import logging

from sqlalchemy.orm import Session

from app.database import SessionLocal, init_db
from app.models.kb_document import KbDocument
from app.services.knowledge_service import KnowledgeService
from app.rag.loader import ALLOWED_UPLOAD_EXTS, SUPPORTED_EXTENSIONS

logger = logging.getLogger(__name__)

# Seed documents go into the default knowledge base.
SEED_KB_ID = "default"

# Supported source extension -> DB file_type enum value.
# 复用 loader 的单一事实来源,避免与上传校验、解析分发出现漂移。
SUPPORTED_EXTS = SUPPORTED_EXTENSIONS

# create_document_record does not persist a user_id column; this is a placeholder
# to satisfy the signature for system-initiated (non-user) ingestion.
SYSTEM_USER_ID = 0


def _seed_docs_dir() -> Path:
    """Locate the seed_docs directory at the project root.

    __file__ = backend/app/services/init_service.py
    parents[3] = project root (…/5day)
    """
    return Path(__file__).resolve().parents[3] / "seed_docs"


def seed_knowledge_base(force: bool = False, kb_id: str = SEED_KB_ID) -> Dict[str, Any]:
    """Ingest every supported document in seed_docs/ into the knowledge base.

    Args:
        force: When True, existing records for a seed file (any status) are
            deleted first and the file is re-ingested. When False (default),
            files already ingested with status == "ready" are skipped.
        kb_id: Target knowledge base id.

    Returns:
        A summary dict: {seeded: [...], skipped: [...], failed: [...],
        seed_dir, vector_count?, error?}.
    """
    seed_dir = _seed_docs_dir()
    result: Dict[str, Any] = {
        "seeded": [],
        "skipped": [],
        "failed": [],
        "seed_dir": str(seed_dir),
    }

    if not seed_dir.exists():
        msg = f"seed_docs directory not found: {seed_dir}"
        logger.warning(msg)
        result["error"] = msg
        return result

    # Ensure tables exist (safe no-op when they were already created by init_db.sql).
    try:
        init_db()
    except Exception as e:  # pragma: no cover - depends on live DB
        logger.error(f"init_db() failed before seeding: {e}")
        result["error"] = f"database not ready: {e}"
        return result

    files = sorted(
        p for p in seed_dir.iterdir()
        if p.is_file() and p.suffix.lower().lstrip(".") in SUPPORTED_EXTS
    )
    if not files:
        supported = "/".join(f".{e}" for e in ALLOWED_UPLOAD_EXTS)
        result["error"] = f"no supported seed documents ({supported}) found"
        logger.warning(result["error"])
        return result

    db: Session = SessionLocal()
    try:
        for path in files:
            name = path.name
            file_type = SUPPORTED_EXTS[path.suffix.lower().lstrip(".")]

            existing = db.query(KbDocument).filter(
                KbDocument.kb_id == kb_id,
                KbDocument.name == name,
            ).all()
            already_ready = any(d.status == "ready" for d in existing)

            if already_ready and not force:
                logger.info(f"[skip] '{name}' already ingested (status=ready)")
                result["skipped"].append(name)
                continue

            # force=True, or leftover processing/failed records: clean up first
            # so vectors and rows stay consistent, then re-ingest.
            for doc in existing:
                try:
                    KnowledgeService.delete_document(db, doc.id)
                    logger.info(f"[cleanup] removed stale record for '{name}' (id={doc.id})")
                except Exception as e:
                    logger.warning(f"[cleanup] failed for '{name}' (id={doc.id}): {e}")
                    db.rollback()

            try:
                content = path.read_bytes()
                document = KnowledgeService.create_document_record(
                    db=db,
                    user_id=SYSTEM_USER_ID,
                    file_name=name,
                    file_type=file_type,
                    file_size=len(content),
                    kb_id=kb_id,
                )
                # Reuse the exact production pipeline: load -> split -> embed -> store.
                KnowledgeService.process_document(db, document.id, content)
                db.refresh(document)

                if document.status == "ready":
                    logger.info(
                        f"[ok] '{name}': {document.chunk_count} chunks, "
                        f"{document.char_count} chars"
                    )
                    result["seeded"].append({
                        "name": name,
                        "chunks": document.chunk_count,
                        "chars": document.char_count,
                    })
                else:
                    logger.error(
                        f"[fail] '{name}': status={document.status} "
                        f"err={document.error_msg}"
                    )
                    result["failed"].append({"name": name, "error": document.error_msg})
            except Exception as e:  # pragma: no cover - depends on live services
                logger.exception(f"[fail] '{name}': {e}")
                result["failed"].append({"name": name, "error": str(e)})
                db.rollback()

        # Report the current vector count for a quick sanity check.
        try:
            from app.rag.vector_store import VectorStore
            result["vector_count"] = VectorStore().get_count()
        except Exception as e:  # pragma: no cover
            logger.warning(f"could not read vector count: {e}")

        return result
    finally:
        db.close()
