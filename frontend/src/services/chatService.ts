import api from "./api";
import type {
  Conversation,
  Message,
  ChatResponse,
  CreateConversationRequest,
  SendMessageRequest,
} from "../types/chat";

export const chatService = {
  async getConversations(): Promise<Conversation[]> {
    const response = await api.get<Conversation[]>("/conversations");
    return response.data;
  },

  async createConversation(
    data: CreateConversationRequest = {}
  ): Promise<Conversation> {
    const response = await api.post<Conversation>("/conversations", data);
    return response.data;
  },

  async getMessages(conversationId: string): Promise<Message[]> {
    const response = await api.get<Message[]>(
      `/conversations/${conversationId}/messages`
    );
    return response.data;
  },

  async sendMessage(
    conversationId: string,
    data: SendMessageRequest
  ): Promise<ChatResponse> {
    const response = await api.post<ChatResponse>(
      `/conversations/${conversationId}/messages`,
      data
    );
    return response.data;
  },
};