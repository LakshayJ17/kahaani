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

export default function Progress({ job }: { job: Job }) {
  const steps = job.action ? STEPS[job.action] : [];
  const current = steps.findIndex((s) => job.step.startsWith(s));
  const waiting = job.queuePosition > 0;

  return (
    <div aria-live="polite">
      <p className="font-display text-2xl text-indigo">
        {waiting ? "Waiting for a free spot" : job.step || "Starting"}
      </p>
      <p className="mt-1 text-ink-soft">
        {waiting
          ? `${job.queuePosition} ${job.queuePosition === 1 ? "book is" : "books are"} being made ahead of yours.`
          : "This usually takes under a minute. You can stay on this page."}
      </p>

      <div
        className="mt-6 h-1.5 w-full overflow-hidden rounded-full bg-line"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(job.progress * 100)}
      >
        <div
          className="h-full rounded-full bg-marigold transition-[width] duration-500 ease-out"
          style={{ width: `${Math.max(4, job.progress * 100)}%` }}
        />
      </div>

      {steps.length > 1 && (
        <ol className="mt-6 space-y-2">
          {steps.map((s, i) => {
            const state = current < 0 ? "todo" : i < current ? "done" : i === current ? "now" : "todo";
            return (
              <li key={s} className="flex items-baseline gap-3">
                <span
                  className={`w-5 text-right text-sm tabular-nums ${
                    state === "todo" ? "text-ink-soft/50" : "text-indigo"
                  }`}
                >
                  {i + 1}
                </span>
                <span
                  className={
                    state === "now"
                      ? "font-medium text-ink"
                      : state === "done"
                        ? "text-ink-soft line-through decoration-line"
                        : "text-ink-soft/60"
                  }
                >
                  {state === "now" ? job.step : s.replace(/ page$/, " the pages")}
                </span>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
