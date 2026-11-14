"use client";

import { useState } from "react";
import { FEEDBACK_TAGS, type Feedback as FeedbackValue, type Taste } from "@/lib/api";

const RATINGS: [FeedbackValue["rating"], string][] = [
  [1, "Loved it"],
  [0, "It was okay"],
  [-1, "Not for us"],
];

interface Props {
  childName: string;
  initial: FeedbackValue | null;
  prominent: boolean; // on the last page, ask more visibly
  onSave: (fb: FeedbackValue) => Promise<Taste>;
}

export default function Feedback({ childName, initial, prominent, onSave }: Props) {
  const [rating, setRating] = useState<FeedbackValue["rating"] | null>(initial?.rating ?? null);
  const [tags, setTags] = useState<string[]>(initial?.tags ?? []);
  const [saved, setSaved] = useState<Taste | null>(null);
  const [saving, setSaving] = useState(false);
  const dirty =
    rating !== (initial?.rating ?? null) ||
    tags.slice().sort().join() !== (initial?.tags ?? []).slice().sort().join();

  const toggle = (t: string) =>
    setTags((cur) => (cur.includes(t) ? cur.filter((x) => x !== t) : [...cur, t]));

  return (
    <section
      aria-labelledby="feedback-title"
      className={`mt-6 rounded-sm px-5 py-5 ${prominent ? "bg-marigold-soft" : "border-t border-line px-0"}`}
    >
      <h2 id="feedback-title" className="font-display text-xl text-indigo">
        How did {childName} like it?
      </h2>
      <p className="mt-1 text-sm text-ink-soft">
        Your answer shapes the next story for {childName}.
      </p>
      <div className="mt-3 flex flex-wrap gap-2" role="radiogroup" aria-label="Rating">
        {RATINGS.map(([value, label]) => (
          <button
            key={value}
            role="radio"
            aria-checked={rating === value}
            onClick={() => {
              setRating(value);
              setSaved(null);
            }}
            className={`rounded-full border px-4 py-1.5 transition-colors ${
              rating === value
                ? "border-indigo bg-indigo text-white"
                : "border-line bg-sheet hover:border-indigo/50"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {rating !== null && (
        <>
          <p className="mt-4 text-sm font-medium">Anything in particular? (optional)</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {FEEDBACK_TAGS.map(([value, label]) => (
              <button
                key={value}
                aria-pressed={tags.includes(value)}
                onClick={() => {
                  toggle(value);
                  setSaved(null);
                }}
                className={`rounded-full border px-3 py-1 text-sm transition-colors ${
                  tags.includes(value)
                    ? "border-leaf bg-leaf text-white"
                    : "border-line bg-sheet hover:border-leaf/60"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="mt-4 flex flex-wrap items-baseline gap-4">
            <button
              disabled={saving || (!dirty && !!initial)}
              onClick={async () => {
                setSaving(true);
                try {
                  setSaved(await onSave({ rating, tags }));
                } finally {
                  setSaving(false);
                }
              }}
              className="rounded-full bg-indigo px-5 py-2 font-medium text-white hover:bg-indigo-deep disabled:opacity-40"
            >
              {initial ? "Update" : "Save"}
            </button>
            {saved && (
              <p className="text-sm" role="status">
                {saved.summary.length
                  ? `Thanks. Next time for ${childName}: ${saved.summary.join(", ")}.`
                  : `Thanks. We'll keep learning what ${childName} enjoys.`}
              </p>
            )}
          </div>
        </>
      )}
    </section>
  );
}
