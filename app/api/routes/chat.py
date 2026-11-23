
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.dependencies import get_current_user

from app.models.user import User
from app.schemas.chat import ChatRequest, ChatResponse, ConversationCreate
from app.schemas.conversation import ConversationResponse
from app.schemas.message import MessageResponse

from app.core.rag import retriever, generation_service
from app.services.chat_service import ChatService


router = APIRouter(tags=["Chat"])

chat_service = ChatService(
    retriever=retriever,
    generation_service=generation_service,
)


@router.post(
    "/conversations",
    response_model=ConversationResponse,
)
def create_conversation(
    data: ConversationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return chat_service.create_conversation(
        db=db,
        user=current_user,
        title=data.title,
    )


@router.get(
    "/conversations",
    response_model=list[ConversationResponse],
)
def list_conversations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return chat_service.list_conversations(
        db=db,
        user=current_user,
    )


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=list[MessageResponse],
)
def get_messages(
    conversation_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conversation = chat_service.get_conversation(
        db=db,
        conversation_id=conversation_id,
        user=current_user,
    )

    if not conversation:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found",
        )

    return chat_service.get_messages(db, conversation)


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=ChatResponse,
)
def send_message(
    conversation_id: UUID,
    data: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conversation = chat_service.get_conversation(
        db=db,
        conversation_id=conversation_id,
        user=current_user,
    )

    if not conversation:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found",
        )

    try:
        result = chat_service.send_message(
            db=db,
            conversation=conversation,
            user=current_user,
            question=data.question,
        )

        return {
            "conversation_id": conversation.id,
            "user_message_id": result["user_message"].id,
            "assistant_message_id": result["assistant_message"].id,
            "answer": result["answer"],
            "citations": result["citations"],
        }

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Unable to generate an answer",
        )
