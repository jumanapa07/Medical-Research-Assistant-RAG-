
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.conversation import Conversation
from app.models.message import Message


class ChatService:

    def __init__(self, retriever, generation_service):
        self.retriever = retriever
        self.generation_service = generation_service

    def create_conversation(
        self,
        db: Session,
        user,
        title: str = "New conversation",
    ):
        conversation = Conversation(
            tenant_id=user.tenant_id,
            user_id=user.id,
            title=title,
        )

        db.add(conversation)
        db.commit()
        db.refresh(conversation)

        return conversation

    def list_conversations(self, db: Session, user):
        return list(
            db.scalars(
                select(Conversation)
                .where(
                    Conversation.user_id == user.id,
                    Conversation.tenant_id == user.tenant_id,
                )
                .order_by(Conversation.created_at.desc())
            ).all()
        )

    def get_conversation(
        self,
        db: Session,
        conversation_id: UUID,
        user,
    ):
        return db.scalar(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.user_id == user.id,
                Conversation.tenant_id == user.tenant_id,
            )
        )

    def get_messages(
        self,
        db: Session,
        conversation: Conversation,
    ):
        return list(
            db.scalars(
                select(Message)
                .where(
                    Message.conversation_id == conversation.id
                )
                .order_by(Message.created_at.asc())
            ).all()
        )

    
    def _get_recent_history(
        self,
        db: Session,
        conversation: Conversation,
        limit: int = 10,
    ) -> list[dict[str, str]]:
        messages = list(
            db.scalars(
                select(Message)
                .where(
                    Message.conversation_id == conversation.id
                )
                .order_by(
                    Message.created_at.desc(),
                    Message.id.desc(),
                )
                .limit(limit)
            ).all()
        )

        # Reverse to restore chronological order.
        messages.reverse()

        return [
            {
                "role": message.role,
                "content": message.content,
            }
            for message in messages
            if message.role in {"user", "assistant"}
        ]

    def send_message(
        self,
        db: Session,
        conversation: Conversation,
        user,
        question: str,
    ):
        # 1. Load previous messages before saving the new question.
        history = self._get_recent_history(
            db=db,
            conversation=conversation,
            limit=10,
        )

        # 2. Save the current user question.
        user_message = Message(
            conversation_id=conversation.id,
            role="user",
            content=question,
        )

        db.add(user_message)
        db.commit()
        db.refresh(user_message)

        try:
            # 3. Rewrite follow-up question for retrieval.
            retrieval_query = self.generation_service.rewrite_query(
                query=question,
                conversation_history=history,
            )

            # 4. Retrieve relevant authorized chunks.
            chunks = self.retriever.retrieve(
                query=retrieval_query,
                tenant_id=str(user.tenant_id),
                owner_id=str(user.id),
            )

            # 5. Generate answer using original question,
            #    conversation history and retrieved chunks.
            result = self.generation_service.generate(
                query=question,
                chunks=chunks,
                conversation_history=history,
            )

            # 6. Save assistant response.
            assistant_message = Message(
                conversation_id=conversation.id,
                role="assistant",
                content=result["answer"],
                citations=result.get("citations", []),
            )

            db.add(assistant_message)
            db.commit()
            db.refresh(assistant_message)

            return {
                "user_message": user_message,
                "assistant_message": assistant_message,
                "answer": result["answer"],
                "citations": result.get("citations", []),
            }

        except Exception:
            db.rollback()
            raise
