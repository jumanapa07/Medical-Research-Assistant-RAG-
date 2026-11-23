import api from "./api";
import type { Document } from "../types/document";

export const documentService = {
  async getDocuments(): Promise<Document[]> {
    const response = await api.get<Document[]>("/documents/");
    return response.data;
  },

  async uploadDocument(file: File): Promise<Document> {
    const formData = new FormData();
    formData.append("file", file);

    const response = await api.post<Document>(
      "/documents/upload",
      formData
    );

    return response.data;
  },

  async deleteDocument(documentId: string): Promise<void> {
    await api.delete(`/documents/${documentId}`);
  },
};