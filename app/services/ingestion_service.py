
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.document import Document
from app.services.ingestion import IngestionPipeline
from app.services.vector_store import QdrantVectorStore


class DocumentIngestionService:

    def __init__(
        self,
        pipeline: IngestionPipeline,
        vector_store: QdrantVectorStore,
    ):
        self.pipeline = pipeline
        self.vector_store = vector_store

    def process_document(self, document_id: str):

        db: Session = SessionLocal()

        try:
            document = db.scalar(
                select(Document).where(
                    Document.id == document_id
                )
            )

            if not document:
                return

            document.status = "processing"
            document.error_message = None
            db.commit()

            metadata = {
                "document_id": str(document.id),
                "tenant_id": str(document.tenant_id),
                "owner_id": str(document.owner_id),
                "title": document.title,
                "version": document.version,
                "visibility": document.visibility,
            }

            self.pipeline.ingest_file(
                file_path=Path(document.file_path),
                metadata=metadata,
                store=self.vector_store,
            )

            document.status = "indexed"
            document.error_message = None
            db.commit()

        except Exception as error:
            print(f"Exception raised: {error}")
            db.rollback()

            document = db.scalar(
                select(Document).where(
                    Document.id == document_id
                )
            )

            if document:
                document.status = "failed"
                document.error_message = str(error)[:4000]
                db.commit()

        finally:
            db.close()
