"use client";

import { AnimatePresence, motion } from "framer-motion";
import { Download, Play, X } from "lucide-react";
import { useEffect, useState } from "react";
import { ButtonAnchor } from "@/components/ui/Button";
import { Placeholder } from "@/components/ui/Loading";
import { Reveal } from "@/components/ui/Reveal";
import { api, url, type Sample } from "@/lib/api";

/** Sample books standing on a wooden shelf; each opens in a read-along player. */
export function Bookshelf() {
  const [samples, setSamples] = useState<Sample[] | null>(null);
  const [open, setOpen] = useState<Sample | null>(null);

  useEffect(() => {
    api
      .samples()
      .then(setSamples)
      .catch(() => setSamples([]));
  }, []);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <section
      id="samples"
      aria-labelledby="shelf-title"
      className="page-x mx-auto max-w-7xl scroll-mt-6 py-16 lg:py-24"
    >
      <Reveal>
        <h2 id="shelf-title" className="text-head">
          From our bookshelf
        </h2>
        <p className="mt-3 max-w-[38rem] text-ink-soft">
          Four books made with Kahaani, in both languages and all three styles.
          Pick one to watch it read aloud.
        </p>

        {samples === null ? (
          <ul
            className="mt-12 grid grid-cols-2 gap-x-6 gap-y-14 px-2 md:grid-cols-4"
            aria-busy="true"
            aria-label="Loading sample books"
          >
            {[0, 1, 2, 3].map((i) => (
              <li key={i}>
                <Placeholder className="aspect-square w-full" />
                <Placeholder className="mt-4 h-5 w-3/4" />
              </li>
            ))}
          </ul>
        ) : (
          <div className="mt-12">
            <ul className="grid grid-cols-2 items-end gap-x-6 gap-y-14 px-2 md:grid-cols-4 md:gap-y-0">
              {samples.map((s, i) => (
                <li key={s.id} className="relative">
                  <button
                    onClick={() => setOpen(s)}
                    className="group block w-full text-left"
                    aria-label={`Read ${s.title}`}
                  >
                    <span
                      className="relative block overflow-hidden rounded-r-xl rounded-l-sm shadow-book transition-transform duration-300 ease-out group-hover:-translate-y-3"
                      style={{ rotate: `${[-1.5, 1, -0.5, 1.5][i % 4]}deg` }}
                    >
                      <img
                        src={url(s.coverUrl)}
                        alt=""
                        className="aspect-[4/5] w-full object-cover"
                      />
                      {/* The spine. */}
                      <span
                        className="absolute inset-y-0 left-0 w-3 bg-black/15"
                        aria-hidden="true"
                      />
                      <span className="absolute bottom-3 right-3 inline-flex items-center gap-1.5 rounded-lg bg-page/95 px-2.5 py-1 text-small font-semibold opacity-0 transition-opacity duration-200 group-hover:opacity-100 group-focus-visible:opacity-100">
                        <Play
                          className="size-3.5 fill-current"
                          strokeWidth={2}
                          aria-hidden="true"
                        />
                        Read along
                      </span>
                    </span>
                  </button>
                  {/* The shelf under this row on phones. */}
                  <span
                    className="mt-0 block h-3 rounded-sm bg-shelf shadow-[0_6px_10px_-4px_rgb(43_33_24_/_0.5)] md:hidden"
                    aria-hidden="true"
                  />
                </li>
              ))}
            </ul>
            <div
              className="hidden h-4 rounded-sm bg-shelf shadow-[0_8px_14px_-6px_rgb(43_33_24_/_0.55)] md:block"
              aria-hidden="true"
            />
            <ul className="mt-5 grid grid-cols-2 gap-x-6 gap-y-6 px-2 md:grid-cols-4">
              {samples.map((s) => (
                <li key={s.id} className="hidden md:block">
                  <p className="font-display text-lead leading-snug">
                    {s.title}
                  </p>
                  <p className="mt-1 text-small text-ink-soft">{s.blurb}</p>
                </li>
              ))}
            </ul>
          </div>
        )}
      </Reveal>

      <AnimatePresence>
        {open && (
          <motion.div
            className="fixed inset-0 z-50 flex items-center justify-center bg-ink/60 p-4"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setOpen(null)}
          >
            <motion.div
              role="dialog"
              aria-modal="true"
              aria-label={open.title}
              className="paper w-[min(60rem,100%)] rounded-2xl p-4 sm:p-6"
              initial={{ opacity: 0, y: 24, rotateX: 8 }}
              animate={{ opacity: 1, y: 0, rotateX: 0 }}
              exit={{ opacity: 0, y: 12 }}
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-start justify-between gap-4">
                <div>
                  <h3 className="text-lead">{open.title}</h3>
                  <p className="text-small text-ink-soft">{open.blurb}</p>
                </div>
                <button
                  onClick={() => setOpen(null)}
                  aria-label="Close"
                  className="rounded-lg p-2 hover:bg-sand"
                >
                  <X className="size-5" strokeWidth={1.75} />
                </button>
              </div>
              {open.videoUrl ? (
                <video
                  src={url(open.videoUrl)}
                  controls
                  autoPlay
                  className="mt-4 w-full rounded-xl bg-ink"
                />
              ) : (
                <img
                  src={url(open.coverUrl)}
                  alt=""
                  className="mt-4 w-full rounded-xl"
                />
              )}
              <ButtonAnchor
                href={url(open.pdfUrl)}
                variant="secondary"
                className="mt-4"
                icon={<Download className="size-4" strokeWidth={1.75} />}
              >
                Open the PDF
              </ButtonAnchor>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
}
