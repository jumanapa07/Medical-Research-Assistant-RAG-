export interface Citation {
  source_number: number;
  source_id: string;
  title: string;
  page_start?: number | null;
  page_end?: number | null;
}

export interface Message {
  id: string;
  conversation_id: string;
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
  created_at: string;
}

export interface Conversation {
  id: string;
  title: string;
  created_at: string;
}

export interface CreateConversationRequest {
  title?: string;
}

export interface SendMessageRequest {
  question: string;
}

export interface ChatResponse {
  conversation_id: string;
  answer: string;
  citations: Citation[];
}