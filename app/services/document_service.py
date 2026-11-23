import hashlib
import os
import uuid

from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document

STORAGE_PATH = Path(os.getenv("DOCUMENT_STORAGE_PATH", "storage/documents"))

MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE_MB", "100")) * 1024 * 1024


class DocumentService:

    @staticmethod
    def upload_document(
        db: Session,
        file: UploadFile,
        user,
        title: str | None = None,
    ) -> Document:

        if not file.filename:
            raise ValueError("Filename is missing")

        # Accept PDF files only.
        safe_filename = file.filename.replace("\\", "/").split("/")[-1]

        if Path(safe_filename).suffix.lower() != ".pdf":
            raise ValueError("Only PDF files are supported")

        document_id = uuid.uuid4()

        # Generate a server-controlled storage path.
        document_dir = STORAGE_PATH / str(user.tenant_id)
        document_dir.mkdir(parents=True, exist_ok=True)

        file_path = document_dir / f"{document_id}.pdf"

        file_hash = hashlib.sha256()
        file_size = 0
        first_bytes = b""

        try:
            with file_path.open("wb") as output:
                while True:
                    chunk = file.file.read(1024 * 1024)

                    if not chunk:
                        break

                    if not first_bytes:
                        first_bytes = chunk[:5]

                    file_size += len(chunk)

                    if file_size > MAX_FILE_SIZE:
                        raise ValueError("File exceeds the maximum allowed size")

                    file_hash.update(chunk)
                    output.write(chunk)

            # Check actual PDF signature, not just extension.
            if first_bytes != b"%PDF-":
                raise ValueError("Invalid PDF file")

            checksum = file_hash.hexdigest()

            # Prevent the same user uploading the same file twice.
            existing = db.scalar(
                select(Document).where(
                    Document.tenant_id == user.tenant_id,
                    Document.owner_id == user.id,
                    Document.file_hash == checksum,
                )
            )

            if existing:
                raise ValueError("You have already uploaded this document")

            document = Document(
                id=document_id,
                tenant_id=user.tenant_id,
                owner_id=user.id,
                title=title or Path(safe_filename).stem,
                original_filename=safe_filename,
                file_path=str(file_path.resolve()),
                file_hash=checksum,
                file_size=file_size,
                status="uploaded",
                visibility="private",
                version=1,
            )

            db.add(document)
            db.commit()
            db.refresh(document)

            return document

        except Exception:
            db.rollback()

            if file_path.exists():
                file_path.unlink()

            raise

    @staticmethod
    def list_documents(
        db: Session,
        user,
    ) -> list[Document]:

        return list(
            db.scalars(
                select(Document)
                .where(
                    Document.tenant_id == user.tenant_id,
                    (
                        (Document.owner_id == user.id)
                        | (Document.visibility == "public")
                    ),
                )
                .order_by(Document.created_at.desc())
            ).all()
        )

    @staticmethod
    def get_document(
        db: Session,
        document_id: uuid.UUID,
        user,
    ) -> Document | None:

        return db.scalar(
            select(Document).where(
                Document.id == document_id,
                Document.tenant_id == user.tenant_id,
                ((Document.owner_id == user.id) | (Document.visibility == "public")),
            )
        )

    @staticmethod
    def delete_document(
        db: Session,
        document_id,
        user,
        vector_store,
    ) -> dict:

        document = db.scalar(
            select(Document)
            .where(
                Document.id == document_id,
                Document.tenant_id == user.tenant_id,
                Document.owner_id == user.id,
            )
            .with_for_update()
        )

        if not document:
            raise ValueError("Document not found")
        
        if document.status == "processing":
            raise RuntimeError(
                "Cannot delete a document while ingestion is running"
            )

        # Mark deletion as in progress.
        document.status = "deleting"
        document.error_message = None
        db.commit()

        try:
            # 1. Remove all vectors belonging to this document.
            vector_store.delete_document(
                tenant_id=str(document.tenant_id),
                document_id=str(document.id),
                keep_chunk_ids=set(),
            )

            # 2. Remove the physical PDF.
            file_path = Path(document.file_path)

            if file_path.exists():
                file_path.unlink()

            # 3. Remove PostgreSQL record.
            db.delete(document)
            db.commit()

            return {
                "document_id": str(document_id),
                "status": "deleted",
            }

        except Exception as error:
            db.rollback()

            # Keep the record so deletion can be retried.
            existing_document = db.scalar(
                select(Document).where(
                    Document.id == document_id,
                    Document.tenant_id == user.tenant_id,
                    Document.owner_id == user.id,
                )
            )

            if existing_document:
                existing_document.status = "failed"
                existing_document.error_message = (
                    f"Deletion failed: {str(error)[:3900]}"
                )
                db.commit()

            raise
