export type DocumentStatus =
  | "uploaded"
  | "processing"
  | "completed"
  | "failed"
  | "deleting";

export interface Document {
  id: string;
  title: string;
  original_filename: string;
  file_size: number;
  status: DocumentStatus;
  visibility: string;
  version: number;
  created_at: string;
  error_message?: string | null;
}