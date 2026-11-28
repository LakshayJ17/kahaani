"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";
import {
  FEEDBACK_TAGS,
  type Feedback as FeedbackValue,
  type Taste,
} from "@/lib/api";

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

export default function Feedback({
  childName,
  initial,
  prominent,
  onSave,
}: Props) {
  const [rating, setRating] = useState<FeedbackValue["rating"] | null>(
    initial?.rating ?? null,
  );
  const [tags, setTags] = useState<string[]>(initial?.tags ?? []);
  const [saved, setSaved] = useState<Taste | null>(null);
  const [saving, setSaving] = useState(false);
  const dirty =
    rating !== (initial?.rating ?? null) ||
    tags.slice().sort().join() !== (initial?.tags ?? []).slice().sort().join();

  const toggle = (t: string) =>
    setTags((cur) =>
      cur.includes(t) ? cur.filter((x) => x !== t) : [...cur, t],
    );

  return (
    <section
      aria-labelledby="feedback-title"
      className={`mt-6 rounded-xl px-5 py-5 ${prominent ? "bg-saffron-soft" : "border-t border-ink/15 px-0"}`}
    >
      <h2 id="feedback-title" className="font-display text-xl text-ink">
        How did {childName} like it?
      </h2>
      <p className="mt-1 text-sm text-ink-soft">
        Your answer shapes the next story for {childName}.
      </p>
      <div
        className="mt-3 flex flex-wrap gap-2"
        role="radiogroup"
        aria-label="Rating"
      >
        {RATINGS.map(([value, label]) => (
          <button
            key={value}
            role="radio"
            aria-checked={rating === value}
            onClick={() => {
              setRating(value);
              setSaved(null);
            }}
            className={`rounded-lg border px-4 py-1.5 transition-colors ${
              rating === value
                ? "border-ink bg-ink text-page"
                : "border-ink/15 bg-page hover:border-ink/40"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {rating !== null && (
        <>
          <p className="mt-4 text-sm font-medium">
            Anything in particular? (optional)
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            {FEEDBACK_TAGS.map(([value, label]) => (
              <button
                key={value}
                aria-pressed={tags.includes(value)}
                onClick={() => {
                  toggle(value);
                  setSaved(null);
                }}
                className={`rounded-lg border px-3 py-1 text-sm transition-colors ${
                  tags.includes(value)
                    ? "border-success bg-success text-white"
                    : "border-ink/15 bg-page hover:border-success/60"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="mt-4 flex flex-wrap items-baseline gap-4">
            <Button
              disabled={!dirty && !!initial}
              loading={saving}
              loadingText="Saving..."
              onClick={async () => {
                setSaving(true);
                try {
                  setSaved(await onSave({ rating, tags }));
                } finally {
                  setSaving(false);
                }
              }}
              className="min-h-10"
            >
              {initial ? "Update" : "Save"}
            </Button>
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
