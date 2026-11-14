import type { QualityCheck } from "@/lib/api";

const STATUS: Record<QualityCheck["status"], { label: string; className: string }> = {
  passed: { label: "Passed", className: "text-leaf" },
  fixed: { label: "Fixed", className: "text-indigo" },
  flagged: { label: "Needs a look", className: "text-alert" },
  skipped: { label: "Not checked", className: "text-ink-soft" },
};

export default function QualityReport({ checks }: { checks: QualityCheck[] }) {
  if (!checks.length) return null;
  const fixed = checks.filter((c) => c.status === "fixed").length;

  return (
    <details className="group mt-6 border-t border-line pt-4">
      <summary className="cursor-pointer list-none font-medium text-indigo [&::-webkit-details-marker]:hidden">
        How this book was checked
        <span className="ml-2 font-normal text-ink-soft">
          {checks.length} checks{fixed ? `, ${fixed} fixed automatically` : ", all passed"}
        </span>
      </summary>
      <p className="mt-3 max-w-[38rem] text-sm text-ink-soft">
        Before you saw this book, a second AI reviewed the words and every picture, and simple
        rules checked for broken images and hidden instructions.
      </p>
      <dl className="mt-3 grid max-w-xl grid-cols-[1fr_auto] gap-x-6 gap-y-1.5 text-[0.95rem]">
        {checks.map((c) => (
          <div key={c.name} className="contents">
            <dt>
              {c.name}
              {c.detail && c.status !== "passed" && (
                <span className="block text-sm text-ink-soft">{c.detail}</span>
              )}
            </dt>
            <dd className={`text-right ${STATUS[c.status].className}`}>{STATUS[c.status].label}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}
