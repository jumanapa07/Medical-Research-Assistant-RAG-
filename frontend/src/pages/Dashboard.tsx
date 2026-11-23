import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function Dashboard() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-slate-50 p-8">
      <div className="mx-auto max-w-5xl">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">
              Medical Research Assistant
            </h1>
            <p className="mt-2 text-slate-600">
              Welcome, {user?.full_name}
            </p>
          </div>

          <button
            onClick={logout}
            className="rounded-lg border border-slate-300 px-4 py-2"
          >
            Logout
          </button>
        </div>

        <div className="mt-10 grid gap-6 md:grid-cols-2">
          <button
            onClick={() => navigate("/documents")}
            className="rounded-xl border border-slate-200 bg-white p-8 text-left hover:border-blue-400"
          >
            <h2 className="text-lg font-semibold">Research Documents</h2>
            <p className="mt-2 text-sm text-slate-500">
              Upload, organize, and manage research papers.
            </p>
          </button>

          <div className="rounded-xl border border-slate-200 bg-white p-8">
            <h2 className="text-lg font-semibold">Research Assistant</h2>
            <p className="mt-2 text-sm text-slate-500">
              Ask questions across your uploaded research papers.
            </p>
            <p className="mt-3 text-xs text-slate-400">
              Chat interface coming next.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}