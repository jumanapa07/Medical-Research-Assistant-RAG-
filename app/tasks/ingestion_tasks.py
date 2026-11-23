from celery import shared_task
from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.rag import ingestion_service
from app.models.document import Document


@shared_task(
    bind=True,
    name="app.tasks.process_document",
    max_retries=3,
)
def process_document_task(self, document_id: str):

    db = SessionLocal()

    try:
        document = db.scalar(
            select(Document).where(
                Document.id == document_id
            )
        )

        if not document:
            return {"status": "not_found"}

        document.status = "processing"
        document.error_message = None
        db.commit()

        ingestion_service.process_document(document_id)

        db.refresh(document)

        if document.status == "failed":
            raise RuntimeError(
                document.error_message or "Document ingestion failed"
            )

        return {
            "document_id": document_id,
            "status": document.status,
        }

    except Exception as exc:
        db.rollback()

        if self.request.retries < self.max_retries:
            raise self.retry(
                exc=exc,
                countdown=2 ** self.request.retries,
            )

        document = db.scalar(
            select(Document).where(
                Document.id == document_id
            )
        )

        if document:
            document.status = "failed"
            document.error_message = str(exc)[:4000]
            db.commit()

        raise

    finally:
        db.close()