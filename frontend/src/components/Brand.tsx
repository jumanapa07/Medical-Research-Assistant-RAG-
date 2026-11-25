export default function Brand({ size = "md" }: { size?: "md" | "lg" }) {
  const box = size === "lg" ? "h-9 w-9" : "h-7 w-7";

  return (
    <div className="flex items-center gap-2.5">
      <div
        className={`${box} flex items-center justify-center rounded-lg bg-teal-700 text-white`}
      >
        <svg
          viewBox="0 0 24 24"
          className="h-4 w-4"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="round"
        >
          <path d="M12 5v14M5 12h14" />
        </svg>
      </div>
      <span className="text-sm font-semibold tracking-tight text-slate-900">
        Medical Research Assistant
      </span>
    </div>
  );
}