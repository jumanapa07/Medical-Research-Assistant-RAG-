import type { ReactNode } from "react";
import Brand from "./Brand";

export const inputClass =
  "w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 outline-none transition focus:border-teal-600 focus:ring-2 focus:ring-teal-600/20";

export const primaryButtonClass =
  "w-full rounded-lg bg-teal-700 py-2.5 text-sm font-medium text-white transition hover:bg-teal-800 disabled:cursor-not-allowed disabled:opacity-50";

export default function AuthLayout({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle: string;
  children: ReactNode;
  footer: ReactNode;
}) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center px-4 py-12">
      <div className="mb-8">
        <Brand size="lg" />
      </div>

      <div className="w-full max-w-sm rounded-xl border border-slate-200 bg-white p-8 shadow-sm">
        <h1 className="text-xl font-semibold tracking-tight text-slate-900">
          {title}
        </h1>
        <p className="mt-1.5 text-sm text-slate-500">{subtitle}</p>

        <div className="mt-6">{children}</div>
      </div>

      <p className="mt-6 text-sm text-slate-500">{footer}</p>
    </div>
  );
}