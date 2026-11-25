import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import AppHeader from "../components/AppHeader";

function ActionCard({
  icon,
  title,
  description,
  onClick,
}: {
  icon: ReactNode;
  title: string;
  description: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="group rounded-xl border border-slate-200 bg-white p-6 text-left transition hover:border-slate-300 hover:shadow-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-600/40"
    >
      <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-slate-100 text-slate-700">
        {icon}
      </div>
      <h2 className="mt-5 text-base font-semibold text-slate-900">{title}</h2>
      <p className="mt-1.5 text-sm leading-6 text-slate-500">{description}</p>
    </button>
  );
}

export default function Dashboard() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const firstName = user?.full_name?.split(" ")[0];

  return (
    <div className="min-h-screen bg-slate-50">
      <AppHeader />

      <main className="mx-auto max-w-6xl px-6 py-10">
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900">
          {firstName ? `Welcome back, ${firstName}` : "Welcome back"}
        </h1>
        <p className="mt-1.5 text-sm text-slate-500">
          Manage your papers or ask questions about them.
        </p>

        <div className="mt-8 grid gap-4 md:grid-cols-2">
          <ActionCard
            onClick={() => navigate("/documents")}
            title="Research documents"
            description="Upload, organize, and manage your research papers."
            icon={
              <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
                <path d="M14 3v5h5M9 13h6M9 17h6" />
              </svg>
            }
          />

          <ActionCard
            onClick={() => navigate("/chat")}
            title="Research assistant"
            description="Ask questions and get answers grounded in your papers, with sources."
            icon={
              <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z" />
              </svg>
            }
          />
        </div>
      </main>
    </div>
  );
}