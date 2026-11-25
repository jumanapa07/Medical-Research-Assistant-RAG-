import { useCallback, useEffect, useState } from "react";
import { documentService } from "../services/documentService";
import type { Document } from "../types/document";
import axios from "axios";
import AppHeader from "../components/AppHeader";

function formatFileSize(bytes: number) {
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }

  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(value: string) {
  return new Date(value).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

const statusStyles: Record<string, { dot: string; label: string }> = {
  uploaded: { dot: "bg-slate-400", label: "Queued" },
  processing: { dot: "bg-amber-500 animate-pulse", label: "Processing" },
  completed: { dot: "bg-emerald-500", label: "Ready" },
  failed: { dot: "bg-red-500", label: "Failed" },
  deleting: { dot: "bg-slate-400 animate-pulse", label: "Deleting" },
};

function StatusBadge({ status }: { status: Document["status"] }) {
  const style = statusStyles[status] ?? { dot: "bg-slate-400", label: status };

  return (
    <span className="inline-flex items-center gap-2 text-sm text-slate-600">
      <span className={`h-2 w-2 rounded-full ${style.dot}`} />
      {style.label}
    </span>
  );
}

export default function Documents() {
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
        setError(err.response?.data?.detail || "Document upload failed.");
      } else {
        setError("Document upload failed.");
      }
    } finally {
      setUploading(false);
    }
  };

  const handleDelete = async (documentId: string) => {
    const confirmed = window.confirm(
      "Delete this document? This also removes it from the assistant's sources."
    );

    if (!confirmed) return;

    try {
      await documentService.deleteDocument(documentId);
      await loadDocuments();
    } catch (err) {
      if (axios.isAxiosError(err)) {
        setError(err.response?.data?.detail || "Unable to delete document.");
      } else {
        setError("Unable to delete document.");
      }
    }
  };

  return (
    <div className="min-h-screen bg-slate-50">
      <AppHeader />

      <main className="mx-auto max-w-6xl px-6 py-10">
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900">
          Documents
        </h1>
        <p className="mt-1.5 text-sm text-slate-500">
          Papers you upload here are used to answer your questions.
        </p>

        <section className="mt-8 rounded-xl border border-slate-200 bg-white p-6">
          <h2 className="text-sm font-semibold text-slate-900">Upload a paper</h2>
          <p className="mt-1 text-sm text-slate-500">PDF files only.</p>

          <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center">
            <input
              id="document-file"
              type="file"
              accept=".pdf,application/pdf"
              onChange={(e) => setSelectedFile(e.target.files?.[0] ?? null)}
              className="block w-full rounded-lg border border-slate-300 bg-white p-1.5 text-sm text-slate-600 file:mr-3 file:rounded-md file:border-0 file:bg-slate-100 file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-slate-700 hover:file:bg-slate-200"
            />

            <button
              onClick={handleUpload}
              disabled={!selectedFile || uploading}
              className="shrink-0 rounded-lg bg-teal-700 px-5 py-2.5 text-sm font-medium text-white transition hover:bg-teal-800 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {uploading ? "Uploading..." : "Upload"}
            </button>
          </div>
        </section>

        {error && (
          <div
            role="alert"
            className="mt-5 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
          >
            {error}
          </div>
        )}

        <section className="mt-10">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-900">
              Your documents
              {documents.length > 0 && (
                <span className="ml-2 font-normal text-slate-400">
                  {documents.length}
                </span>
              )}
            </h2>

            <button
              onClick={loadDocuments}
              className="text-sm font-medium text-slate-600 hover:text-slate-900"
            >
              Refresh
            </button>
          </div>

          {loading ? (
            <p className="py-12 text-center text-sm text-slate-500">
              Loading documents...
            </p>
          ) : documents.length === 0 ? (
            <div className="rounded-xl border border-dashed border-slate-300 bg-white py-14 text-center">
              <p className="text-sm font-medium text-slate-900">
                No documents yet
              </p>
              <p className="mt-1 text-sm text-slate-500">
                Upload a PDF above to start building your library.
              </p>
            </div>
          ) : (
            <ul className="divide-y divide-slate-200 overflow-hidden rounded-xl border border-slate-200 bg-white">
              {documents.map((doc) => (
                <li
                  key={doc.id}
                  className="flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-slate-900">
                      {doc.title || doc.original_filename}
                    </p>
                    <p className="mt-0.5 truncate text-sm text-slate-500">
                      {doc.original_filename} · {formatFileSize(doc.file_size)} ·{" "}
                      {formatDate(doc.created_at)}
                    </p>

                    {doc.status === "failed" && doc.error_message && (
                      <p className="mt-1.5 text-sm text-red-600">
                        {doc.error_message}
                      </p>
                    )}
                  </div>

                  <div className="flex shrink-0 items-center gap-6">
                    <StatusBadge status={doc.status} />

                    <button
                      onClick={() => handleDelete(doc.id)}
                      disabled={
                        doc.status === "processing" || doc.status === "deleting"
                      }
                      className="text-sm font-medium text-slate-500 transition hover:text-red-600 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:text-slate-500"
                    >
                      Delete
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      </main>
    </div>
  );
}