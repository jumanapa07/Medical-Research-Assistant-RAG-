
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)

from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.dependencies import get_current_user
from app.models.user import User
from app.schemas.document import DocumentResponse
from app.services.document_service import DocumentService
from app.tasks.ingestion_tasks import process_document_task
from app.core.rag import vector_store

router = APIRouter(
    prefix="/documents",
    tags=["Documents"],
)


@router.post(
    "/upload",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
def upload_document(
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        document = DocumentService.upload_document(
            db=db,
            file=file,
            user=current_user,
            title=title,
        )

        process_document_task.delay(str(document.id))

        return document

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        )

@router.get(
    "/",
    response_model=list[DocumentResponse],
)
def list_documents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    
    return DocumentService.list_documents(
        db=db,
        user=current_user,
    )


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
)
def get_document(
    document_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    document = DocumentService.get_document(
        db=db,
        document_id=document_id,
        user=current_user,
    )
    print(current_user,document_id)

    if not document:
        raise HTTPException(
            status_code=404,
            detail="Document not found",
        )

    return document


@router.delete("/{document_id}")
def delete_document(
    document_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return DocumentService.delete_document(
            db=db,
            document_id=document_id,
            user=current_user,
            vector_store=vector_store,
        )

    except ValueError:
        raise HTTPException(
            status_code=404,
            detail="Document not found",
        )

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Unable to delete document",
        )

