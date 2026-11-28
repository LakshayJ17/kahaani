"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function Consent() {
  const { refresh } = useAuth();
  const [agreed, setAgreed] = useState(false);
  const [saving, setSaving] = useState(false);

  return (
    <div className="max-w-2xl rounded-xl border border-ink/15 bg-page p-6 sm:p-8">
      <h3 className="text-2xl text-ink">Before your first book</h3>
      <div className="mt-4 space-y-3 text-ink-soft">
        <p>
          Kahaani saves the books you make to your library: the story, the
          pictures and the narration. Only you can open them. You can delete a
          book, or your whole account and everything in it, at any time.
        </p>
        <p>
          To make books faster for everyone, a copy of each new story is kept
          with the child&apos;s name removed. Another family asking for a very
          similar story may get it, with their own child&apos;s name. The
          pictures are always fictional drawings made from the words you type;
          no photos are ever used.
        </p>
      </div>
      <label className="mt-6 flex items-start gap-3">
        <input
          type="checkbox"
          checked={agreed}
          onChange={(e) => setAgreed(e.target.checked)}
          className="mt-1.5 h-4 w-4 accent-[var(--saffron-deep)]"
        />
        <span>
          I am the parent or guardian, and I agree that Kahaani stores my books
          as described above and in the{" "}
          <a
            href="/privacy/"
            target="_blank"
            className="text-ink underline underline-offset-4"
          >
            privacy policy
          </a>
          .
        </span>
      </label>
      <Button
        disabled={!agreed}
        loading={saving}
        loadingText="Saving..."
        onClick={async () => {
          setSaving(true);
          try {
            await api.consent();
            await refresh();
          } finally {
            setSaving(false);
          }
        }}
        className="mt-6"
      >
        Agree and continue
      </Button>
    </div>
  );
}
