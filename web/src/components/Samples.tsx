"use client";

import { useEffect, useRef, useState } from "react";
import { api, url, type Sample } from "@/lib/api";

export default function Samples() {
  const [samples, setSamples] = useState<Sample[] | null>(null);
  const [open, setOpen] = useState<Sample | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    api.samples().then(setSamples).catch(() => setSamples([]));
  }, []);

  useEffect(() => {
    if (open) dialog.current?.showModal();
  }, [open]);

  if (samples === null) return <div className="h-64" aria-busy="true" />;
  if (!samples.length) return <p className="text-ink-soft">Sample books will appear here.</p>;

  return (
    <>
      <ul className="grid grid-cols-2 gap-x-6 gap-y-10 md:grid-cols-4">
        {samples.map((s) => (
          <li key={s.id}>
            <button onClick={() => setOpen(s)} className="group block w-full text-left">
              <img
                src={url(s.coverUrl)}
                alt=""
                className="aspect-square w-full rounded-sm object-cover shadow-[0_18px_36px_-24px_rgba(23,24,28,0.5)] transition-transform duration-300 group-hover:-translate-y-1"
              />
              <span className="mt-3 block font-display text-lg leading-snug text-indigo group-hover:underline">
                {s.title}
              </span>
              <span className="mt-0.5 block text-sm text-ink-soft">{s.blurb}</span>
            </button>
          </li>
        ))}
      </ul>

      <dialog
        ref={dialog}
        onClose={() => setOpen(null)}
        onClick={(e) => e.target === dialog.current && dialog.current?.close()}
        className="m-auto w-[min(56rem,calc(100vw-2rem))] rounded-sm bg-paper p-0 backdrop:bg-ink/60"
      >
        {open && (
          <div className="p-5 sm:p-7">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h3 className="text-2xl text-indigo">{open.title}</h3>
                <p className="text-sm text-ink-soft">{open.blurb}</p>
              </div>
              <button
                onClick={() => dialog.current?.close()}
                className="rounded-full px-3 py-1 text-ink-soft hover:bg-ink/5 hover:text-ink"
              >
                Close
              </button>
            </div>
            {open.videoUrl ? (
              <video src={url(open.videoUrl)} controls autoPlay className="mt-4 w-full rounded-sm bg-ink" />
            ) : (
              <img src={url(open.coverUrl)} alt="" className="mt-4 w-full rounded-sm" />
            )}
            <a
              href={url(open.pdfUrl)}
              className="mt-4 inline-block rounded-full bg-indigo px-6 py-2.5 font-medium text-white hover:bg-indigo-deep"
            >
              Open the PDF
            </a>
          </div>
        )}
      </dialog>
    </>
  );
}
