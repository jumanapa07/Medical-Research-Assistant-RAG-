import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { documentService } from "../services/documentService";
import { useAuth } from "../context/AuthContext";
import type { Document } from "../types/document";
import axios from "axios";

function formatFileSize(bytes: number) {
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }

  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(value: string) {
  return new Date(value).toLocaleDateString();
}

function StatusBadge({ status }: { status: Document["status"] }) {
  const styles: Record<string, string> = {
    uploaded: "bg-slate-100 text-slate-700",
    processing: "bg-blue-100 text-blue-700",
    completed: "bg-green-100 text-green-700",
    failed: "bg-red-100 text-red-700",
    deleting: "bg-amber-100 text-amber-700",
  };

  return (
    <span
      className={`rounded-full px-3 py-1 text-xs font-medium ${
        styles[status] ?? "bg-slate-100 text-slate-700"
      }`}
    >
      {status}
    </span>
  );
}

export default function Documents() {
  const navigate = useNavigate();
  const { logout } = useAuth();

  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  const loadDocuments = useCallback(async () => {
    try {
      const data = await documentService.getDocuments();
      setDocuments(data);
      setError("");
    } catch {
      setError("Unable to load documents.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDocuments();
  }, [loadDocuments]);

  // Refresh while any document is still being processed.
  useEffect(() => {
    const hasPendingDocuments = documents.some(
      (doc) => doc.status === "uploaded" || doc.status === "processing"
    );

    if (!hasPendingDocuments) return;

    const interval = window.setInterval(loadDocuments, 4000);

    return () => window.clearInterval(interval);
  }, [documents, loadDocuments]);

  const handleUpload = async () => {
    if (!selectedFile) return;

    if (!selectedFile.name.toLowerCase().endsWith(".pdf")) {
      setError("Only PDF files are supported.");
      return;
    }

    setUploading(true);
    setError("");

    try {
      await documentService.uploadDocument(selectedFile);
      setSelectedFile(null);

      const fileInput = document.getElementById(
        "document-file"
      ) as HTMLInputElement | null;

      if (fileInput) fileInput.value = "";

      await loadDocuments();
    } catch (err) {
      if (axios.isAxiosError(err)) {
        setError(
          err.response?.data?.detail || "Document upload failed."
        );
      } else {
        setError("Document upload failed.");
      }
    } finally {
      setUploading(false);
    }
  };

  const handleDelete = async (documentId: string) => {
    const confirmed = window.confirm(
      "Are you sure you want to delete this document?"
    );

    if (!confirmed) return;

    try {
      await documentService.deleteDocument(documentId);
      await loadDocuments();
    } catch (err) {
      if (axios.isAxiosError(err)) {
        setError(
          err.response?.data?.detail || "Unable to delete document."
        );
      } else {
        setError("Unable to delete document.");
      }
    }
  };

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <div>
            <h1 className="text-xl font-bold text-slate-900">
              Medical Research Assistant
            </h1>
            <p className="text-sm text-slate-500">
              Research document workspace
            </p>
          </div>

          <div className="flex gap-3">
            <button
              onClick={() => navigate("/dashboard")}
              className="rounded-lg border px-4 py-2 text-sm hover:bg-slate-50"
            >
              Dashboard
            </button>

            <button
              onClick={logout}
              className="rounded-lg border px-4 py-2 text-sm hover:bg-slate-50"
            >
              Logout
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-8">
        <div className="mb-8">
          <h2 className="text-2xl font-bold text-slate-900">
            Research Documents
          </h2>
          <p className="mt-2 text-slate-500">
            Upload and manage the documents used by your research assistant.
          </p>
        </div>

        <section className="rounded-xl border border-slate-200 bg-white p-6">
          <h3 className="font-semibold text-slate-900">
            Upload a research paper
          </h3>

          <p className="mt-1 text-sm text-slate-500">
            Select a PDF file to add it to your research workspace.
          </p>

          <div className="mt-5 flex flex-col gap-3 sm:flex-row">
            <input
              id="document-file"
              type="file"
              accept=".pdf,application/pdf"
              onChange={(e) =>
                setSelectedFile(e.target.files?.[0] ?? null)
              }
              className="block w-full rounded-lg border border-slate-300 p-2 text-sm"
            />

            <button
              onClick={handleUpload}
              disabled={!selectedFile || uploading}
              className="rounded-lg bg-blue-600 px-6 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {uploading ? "Uploading..." : "Upload PDF"}
            </button>
          </div>
        </section>

        {error && (
          <div className="mt-5 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            {error}
          </div>
        )}

        <section className="mt-8">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-lg font-semibold text-slate-900">
              Your documents
            </h3>

            <button
              onClick={loadDocuments}
              className="text-sm font-medium text-blue-600 hover:text-blue-700"
            >
              Refresh
            </button>
          </div>

          {loading ? (
            <p className="py-10 text-center text-slate-500">
              Loading documents...
            </p>
          ) : documents.length === 0 ? (
            <div className="rounded-xl border border-dashed border-slate-300 bg-white py-14 text-center">
              <p className="font-medium text-slate-700">
                No documents uploaded yet
              </p>
              <p className="mt-2 text-sm text-slate-500">
                Upload a PDF to begin building your research library.
              </p>
            </div>
          ) : (
            <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
              <div className="divide-y divide-slate-200">
                {documents.map((doc) => (
                  <div
                    key={doc.id}
                    className="flex flex-col gap-4 p-5 sm:flex-row sm:items-center sm:justify-between"
                  >
                    <div className="min-w-0">
                      <p className="truncate font-medium text-slate-900">
                        {doc.title || doc.original_filename}
                      </p>

                      <p className="mt-1 text-sm text-slate-500">
                        {doc.original_filename} ·{" "}
                        {formatFileSize(doc.file_size)} ·{" "}
                        {formatDate(doc.created_at)}
                      </p>

                      {doc.status === "failed" && doc.error_message && (
                        <p className="mt-2 text-sm text-red-600">
                          {doc.error_message}
                        </p>
                      )}
                    </div>

                    <div className="flex items-center gap-4">
                      <StatusBadge status={doc.status} />

                      <button
                        onClick={() => handleDelete(doc.id)}
                        disabled={
                          doc.status === "processing" ||
                          doc.status === "deleting"
                        }
                        className="text-sm font-medium text-red-600 hover:text-red-700 disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}