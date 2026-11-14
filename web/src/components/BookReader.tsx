"use client";

import { AnimatePresence, motion } from "framer-motion";
import {
  ChevronLeft,
  ChevronRight,
  Download,
  Flag,
  MoreHorizontal,
  PencilLine,
  Play,
  RotateCcw,
  Trash2,
  X,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Button, ButtonAnchor } from "@/components/ui/Button";
import {
  url,
  type Feedback as FeedbackValue,
  type SavedBook,
  type Taste,
} from "@/lib/api";
import { OpenBook } from "./book/OpenBook";
import Feedback from "./Feedback";

const MOOD_BG: Record<string, string> = {
  happy: "bg-mood-happy",
  curious: "bg-mood-curious",
  worried: "bg-mood-worried",
  brave: "bg-mood-brave",
  calm: "bg-mood-calm",
  proud: "bg-mood-proud",
};

interface Props {
  book: SavedBook;
  onRedo: (page: number, request: string) => void;
  onPage?: (page: number, finished: boolean) => void;
  onReport?: () => void;
  onDelete?: () => void;
  onFeedback?: (fb: FeedbackValue) => Promise<Taste>;
}

export default function BookReader({
  book,
  onRedo,
  onPage,
  onReport,
  onDelete,
  onFeedback,
}: Props) {
  const pages = book.pages;
  const last = pages.length - 1;
  // Open where they left off (unless they finished it, then start again).
  const start =
    book.progressPage >= pages.length ? 0 : Math.max(0, book.progressPage - 1);
  const [[index, direction], setPage] = useState<[number, number]>([start, 0]);
  const [editing, setEditing] = useState(false);
  const [request, setRequest] = useState("");
  const [watching, setWatching] = useState(false);
  const [menu, setMenu] = useState(false);
  const finishedRef = useRef(false);
  const page = pages[Math.min(index, last)];

  const goTo = useCallback(
    (next: number) => {
      setPage(([i]) => {
        const n = Math.max(0, Math.min(last, next));
        return [n, n > i ? 1 : -1];
      });
      setEditing(false);
    },
    [last],
  );
  const go = useCallback((delta: number) => goTo(index + delta), [goTo, index]);

  // Save reading progress; reaching the last page counts as one full read.
  useEffect(() => {
    if (!onPage) return;
    const atEnd = index === last;
    const t = setTimeout(() => {
      onPage(index + 1, atEnd && !finishedRef.current);
      if (atEnd) finishedRef.current = true;
    }, 800);
    return () => clearTimeout(t);
  }, [index, last, onPage]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.closest("input, textarea")) return;
      if (e.key === "Escape") {
        setWatching(false);
        setMenu(false);
      }
      if (watching) return;
      if (e.key === "ArrowRight") go(1);
      if (e.key === "ArrowLeft") go(-1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [go, watching]);

  if (!page) return null;

  return (
    <div>
      <p className="text-ink-soft">{book.forLine}</p>
      <h1 className="mt-1 text-head" lang={book.language}>
        {book.title}
      </h1>

      {/* Actions first, so they're easy to find. */}
      <div className="mt-6 flex flex-wrap items-center gap-2 sm:gap-3">
        <Button
          onClick={() => setWatching(true)}
          icon={<Play className="size-4 fill-current" strokeWidth={1.5} />}
        >
          Watch the read-along
        </Button>
        <ButtonAnchor
          href={url(`${book.pdfUrl}&download=1`)}
          variant="secondary"
          icon={<Download className="size-4" strokeWidth={1.5} />}
        >
          PDF
        </ButtonAnchor>
        <ButtonAnchor
          href={url(`${book.videoUrl}&download=1`)}
          variant="secondary"
          icon={<Download className="size-4" strokeWidth={1.5} />}
        >
          Video
        </ButtonAnchor>
        <Button
          variant="secondary"
          onClick={() => setEditing((v) => !v)}
          aria-expanded={editing}
          icon={<PencilLine className="size-4" strokeWidth={1.5} />}
        >
          Change page {page.number}
        </Button>
        {(onReport || onDelete) && (
          <div className="relative">
            <button
              onClick={() => setMenu((v) => !v)}
              aria-label="More"
              aria-expanded={menu}
              className="flex size-12 items-center justify-center rounded-full bg-sand transition-colors hover:bg-[#e2d1b2]"
            >
              <MoreHorizontal className="size-5" strokeWidth={1.5} />
            </button>
            <AnimatePresence>
              {menu && (
                <motion.ul
                  className="absolute right-0 z-20 mt-2 w-60 rounded-2xl bg-page p-2 shadow-book"
                  initial={{ opacity: 0, y: -6 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -6 }}
                >
                  {onReport && (
                    <li>
                      <button
                        disabled={book.reported}
                        onClick={() => {
                          setMenu(false);
                          onReport();
                        }}
                        className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left hover:paper disabled:opacity-60"
                      >
                        <Flag
                          className="size-4"
                          strokeWidth={1.5}
                          aria-hidden="true"
                        />
                        {book.reported
                          ? "Reported, thank you"
                          : "Report a problem"}
                      </button>
                    </li>
                  )}
                  {onDelete && (
                    <li>
                      <button
                        onClick={() => {
                          setMenu(false);
                          onDelete();
                        }}
                        className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-danger hover:paper"
                      >
                        <Trash2
                          className="size-4"
                          strokeWidth={1.5}
                          aria-hidden="true"
                        />
                        Delete this book
                      </button>
                    </li>
                  )}
                </motion.ul>
              )}
            </AnimatePresence>
          </div>
        )}
      </div>

      <AnimatePresence initial={false}>
        {editing && (
          <motion.form
            className="overflow-hidden"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            onSubmit={(e) => {
              e.preventDefault();
              onRedo(page.number, request);
              setEditing(false);
              setRequest("");
            }}
          >
            <div className="mt-4 rounded-2xl paper p-5">
              <label htmlFor="redo" className="font-medium">
                What should change on page {page.number}?
              </label>
              <textarea
                id="redo"
                rows={2}
                maxLength={200}
                autoFocus
                value={request}
                onChange={(e) => setRequest(e.target.value)}
                placeholder="For example: make it funnier, or add the grandmother"
                className="mt-2 w-full rounded-xl border border-ink/15 bg-page px-3.5 py-2.5 focus:border-saffron-deep focus:outline-none"
              />
              <div className="mt-3 flex flex-wrap items-center gap-3">
                <Button type="submit">Rewrite page {page.number}</Button>
                <Button
                  type="button"
                  variant="quiet"
                  onClick={() => setEditing(false)}
                >
                  Cancel
                </Button>
                <span className="text-small text-ink-soft">
                  Leave it empty for a fresh version of the same page.
                </span>
              </div>
            </div>
          </motion.form>
        )}
      </AnimatePresence>

      {/* The spread: an open book whose leaf turns in the reading direction. */}
      <OpenBook
        className="mt-8"
        turnKey={`${page.number}-${page.imageUrl}`}
        direction={direction === -1 ? -1 : 1}
        rightClassName={MOOD_BG[page.mood] ?? ""}
        left={
          <div className="flex h-full items-center p-3 sm:p-5">
            <img
              src={url(page.imageUrl)}
              alt={`Illustration for page ${page.number}`}
              className="aspect-square w-full rounded-[3px] bg-sand object-cover shadow-[0_1px_2px_rgb(43_33_24/0.25)]"
            />
          </div>
        }
        right={
          <div className="flex h-full items-center px-7 pb-12 pt-8 sm:px-12 md:pl-16">
            <p
              lang={book.language}
              className={`font-display leading-relaxed ${
                book.language === "hi" ? "text-[1.45rem]" : "text-[1.4rem]"
              }`}
            >
              {page.text}
            </p>
          </div>
        }
      />

      <div className="mt-4 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-2">
          <button
            onClick={() => go(-1)}
            disabled={index === 0}
            aria-label="Previous page"
            className="flex size-12 items-center justify-center rounded-full bg-sand transition-[background-color,transform,opacity] hover:bg-[#e2d1b2] active:scale-95 disabled:opacity-35"
          >
            <ChevronLeft className="size-6" strokeWidth={1.5} />
          </button>
          <span className="min-w-[7.5rem] text-center text-small tabular-nums text-ink-soft">
            Page {page.number} of {pages.length}
          </span>
          {index < last ? (
            <button
              onClick={() => go(1)}
              aria-label="Next page"
              className="flex size-12 items-center justify-center rounded-full bg-ink text-page transition-[background-color,transform] hover:bg-[#3d3024] active:scale-95"
            >
              <ChevronRight className="size-6" strokeWidth={1.5} />
            </button>
          ) : (
            <button
              onClick={() => {
                finishedRef.current = false;
                goTo(0);
              }}
              className="inline-flex h-12 items-center gap-2 rounded-full bg-ink px-5 text-small font-medium text-page transition-colors hover:bg-[#3d3024]"
            >
              <RotateCcw
                className="size-4"
                strokeWidth={1.5}
                aria-hidden="true"
              />
              Read again
            </button>
          )}
        </div>
        <div className="flex gap-2 overflow-x-auto pb-1" aria-label="All pages">
          {pages.map((p, i) => (
            <button
              key={p.number}
              onClick={() => goTo(i)}
              aria-label={`Go to page ${p.number}`}
              aria-current={i === index}
              className={`w-14 shrink-0 overflow-hidden rounded-xl ring-2 transition-[opacity,box-shadow] ${
                i === index
                  ? "ring-saffron-deep"
                  : "opacity-60 ring-transparent hover:opacity-100"
              }`}
            >
              <img
                src={url(p.imageUrl)}
                alt=""
                className="aspect-square w-full object-cover"
              />
            </button>
          ))}
        </div>
      </div>

      {!!book.warnings?.length && (
        <div className="mt-6 rounded-2xl bg-saffron-soft px-5 py-4 text-body">
          {book.warnings.map((w) => (
            <p key={w}>{w}</p>
          ))}
        </div>
      )}

      {onFeedback && (
        <Feedback
          childName={book.childName}
          initial={book.feedback}
          prominent={index === last}
          onSave={onFeedback}
        />
      )}

      <AnimatePresence>
        {watching && (
          <motion.div
            className="fixed inset-0 z-50 flex items-center justify-center bg-ink/75 p-4"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setWatching(false)}
          >
            <motion.div
              role="dialog"
              aria-modal="true"
              aria-label={`Read-along: ${book.title}`}
              className="w-[min(64rem,100%)] rounded-2xl bg-page p-3 sm:p-4"
              initial={{ opacity: 0, y: 24, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 12, scale: 0.98 }}
              onClick={(e) => e.stopPropagation()}
            >
              <div className="mb-3 flex items-center justify-between gap-4 px-1">
                <p className="text-body font-medium" lang={book.language}>
                  {book.title}
                </p>
                <button
                  onClick={() => setWatching(false)}
                  aria-label="Close"
                  className="rounded-full p-2 hover:bg-sand"
                >
                  <X className="size-5" strokeWidth={1.5} />
                </button>
              </div>
              <video
                src={url(book.videoUrl)}
                controls
                autoPlay
                className="w-full rounded-xl bg-ink"
              />
              <p className="mt-2 px-1 text-small text-ink-soft">
                The video is put together when you first open it, which can take
                a few seconds.
              </p>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
