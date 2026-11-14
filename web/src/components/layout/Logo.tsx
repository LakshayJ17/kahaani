/** An open book with a saffron ribbon, and the wordmark in Baloo 2. */
export function LogoMark({ className = "size-8" }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden="true">
      <path
        d="M16 9c-3.6-2.4-7.8-3-12-2.2v17.4c4.2-.8 8.4-.2 12 2.2z"
        fill="#fffbf2"
      />
      <path
        d="M16 9c3.6-2.4 7.8-3 12-2.2v17.4c-4.2-.8-8.4-.2-12 2.2z"
        fill="#fffbf2"
      />
      <path
        d="M16 9c-3.6-2.4-7.8-3-12-2.2v17.4c4.2-.8 8.4-.2 12 2.2 3.6-2.4 7.8-3 12-2.2V6.8C23.8 6 19.6 6.6 16 9zM16 9v17.4"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
      <path d="M21 7.4v9l1.8-1.5 1.8 1.5V7.1" fill="#f2a33a" />
    </svg>
  );
}

export function Wordmark({ className = "" }: { className?: string }) {
  return (
    <span className={`inline-flex items-center gap-2 ${className}`}>
      <LogoMark />
      <span className="font-display text-[1.65rem] font-bold leading-none tracking-[-0.01em]">
        kahaani
      </span>
    </span>
  );
}
