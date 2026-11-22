
import hashlib
import os
import uuid

from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document


STORAGE_PATH = Path(
    os.getenv("DOCUMENT_STORAGE_PATH", "storage/documents")
)

MAX_FILE_SIZE = int(
    os.getenv("MAX_FILE_SIZE_MB", "100")
) * 1024 * 1024


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
        safe_filename = (
            file.filename.replace("\\", "/").split("/")[-1]
        )

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
                        raise ValueError(
                            "File exceeds the maximum allowed size"
                        )

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
                raise ValueError(
                    "You have already uploaded this document"
                )

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
                (
                    (Document.owner_id == user.id)
                    | (Document.visibility == "public")
                ),
            )
        )
