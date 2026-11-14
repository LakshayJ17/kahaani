import { Check } from "lucide-react";
import type { Job } from "@/lib/api";

// The steps each action goes through, matching the messages the API reports.
const STEPS: Record<NonNullable<Job["action"]>, string[]> = {
  start: [
    "Checking the details",
    "Looking for a matching story",
    "Writing the story",
    "Reviewing the story",
    "Drawing the hero",
  ],
  hero: ["Drawing another hero"],
  finish: [
    "Drawing page",
    "Checking the pictures",
    "Recording the voice",
    "Making the book",
    "Making the video",
    "Saving to your library",
  ],
  redo: [
    "Checking your request",
    "Rewriting page",
    "Reviewing the new page",
    "Drawing page",
    "Recording the voice",
    "Making the book",
    "Making the video",
  ],
};

const LABEL: Record<string, string> = {
  "Drawing page": "Drawing the pages",
  "Rewriting page": "Rewriting the page",
};

export default function Progress({ job }: { job: Job }) {
  const steps = job.action ? STEPS[job.action] : [];
  const current = steps.findIndex((s) => job.step.startsWith(s));
  const waiting = job.queuePosition > 0;

  return (
    <div aria-live="polite">
      <p className="text-lead">
        {waiting ? "Waiting for a free spot" : job.step || "Starting"}
      </p>
      <p className="mt-1 text-body text-ink-soft">
        {waiting
          ? `${job.queuePosition} ${job.queuePosition === 1 ? "book is" : "books are"} being made ahead of yours.`
          : "This usually takes about a minute. You can stay on this page."}
      </p>

      <div
        className="mt-6 h-1.5 w-full overflow-hidden rounded-full bg-sand"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(job.progress * 100)}
      >
        <div
          className="h-full rounded-full bg-saffron transition-[width] duration-500 ease-out"
          style={{ width: `${Math.max(4, job.progress * 100)}%` }}
        />
      </div>

      {steps.length > 1 && (
        <ol className="mt-6 space-y-3">
          {steps.map((s, i) => {
            const state =
              current < 0
                ? "todo"
                : i < current
                  ? "done"
                  : i === current
                    ? "now"
                    : "todo";
            return (
              <li key={s} className="flex items-center gap-3">
                <span
                  aria-hidden="true"
                  className={`flex size-6 shrink-0 items-center justify-center rounded-full text-small ${
                    state === "done"
                      ? "bg-success text-page"
                      : state === "now"
                        ? "bg-saffron text-ink"
                        : "bg-sand text-ink-soft"
                  }`}
                >
                  {state === "done" ? (
                    <Check className="size-3.5" strokeWidth={2.5} />
                  ) : (
                    i + 1
                  )}
                </span>
                <span
                  className={
                    state === "todo"
                      ? "text-ink-soft"
                      : state === "now"
                        ? "font-medium"
                        : ""
                  }
                >
                  {state === "now" ? job.step : (LABEL[s] ?? s)}
                  {state === "done" && <span className="sr-only"> (done)</span>}
                </span>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
