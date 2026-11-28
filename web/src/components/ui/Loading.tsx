"use client";

import { useEffect, useState } from "react";

/**
 * A small book with a turning page and a short line of text. If loading takes a while (the
 * server may be waking up after a quiet spell), a second line explains the wait.
 */
export function Loading({
  label = "Loading",
  className = "",
}: {
  label?: string;
  className?: string;
}) {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setSlow(true), 6000);
    return () => clearTimeout(t);
  }, []);
  return (
    <div
      role="status"
      aria-live="polite"
      className={`flex flex-col items-center justify-center gap-4 py-16 text-center ${className}`}
    >
      <div className="loader-book" aria-hidden="true">
        <span className="loader-left" />
        <span className="loader-right" />
        <span className="loader-leaf" />
      </div>
      <p className="font-display text-lead">{label}...</p>
      {slow && (
        <p className="max-w-xs text-small text-ink-soft">
          This is taking a little longer than usual. The server may be waking
          up, which can take up to a minute.
        </p>
      )}
    </div>
  );
}

/** A soft pulsing block that holds the space of content still on its way. */
export function Placeholder({ className = "" }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={`animate-pulse rounded-xl bg-sand/70 ${className}`}
    />
  );
}
