"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { url, type Feedback as FeedbackValue, type SavedBook, type Taste } from "@/lib/api";
import Feedback from "./Feedback";
import QualityReport from "./QualityReport";

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
  const start = book.progressPage >= pages.length ? 0 : Math.max(0, book.progressPage - 1);
  const [index, setIndex] = useState(start);
  const [editing, setEditing] = useState(false);
  const [request, setRequest] = useState("");
  const [showVideo, setShowVideo] = useState(false);
  const finishedRef = useRef(false);
  const page = pages[Math.min(index, last)];

  const go = useCallback(
    (delta: number) => {
      setIndex((i) => Math.max(0, Math.min(last, i + delta)));
      setEditing(false);
    },
    [last],
  );

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
      if (e.key === "ArrowRight") go(1);
      if (e.key === "ArrowLeft") go(-1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [go]);

  if (!page) return null;

  return (
    <div>
      <p className="text-ink-soft">{book.forLine}</p>
      <h1 className="mt-1 text-3xl text-indigo sm:text-4xl" lang={book.language}>
        {book.title}
      </h1>

      <div
        key={`${page.number}-${page.imageUrl}`}
        className="page-in mt-5 grid overflow-hidden rounded-sm bg-sheet shadow-[0_24px_50px_-30px_rgba(23,24,28,0.5)] sm:grid-cols-[1.6fr_1fr]"
      >
        <img
          src={url(page.imageUrl)}
          alt={`Illustration for page ${page.number}`}
          className="aspect-square w-full bg-line object-cover"
        />
        <div className={`flex flex-col justify-center p-6 sm:p-8 ${MOOD_BG[page.mood] ?? ""}`}>
          <p
            lang={book.language}
            className={`leading-relaxed ${book.language === "hi" ? "text-xl" : "text-lg"}`}
          >
            {page.text}
          </p>
        </div>
      </div>

      <div className="mt-4 flex items-center justify-between gap-3">
        <button
          onClick={() => go(-1)}
          disabled={index === 0}
          className="rounded-full px-4 py-2 font-medium text-indigo hover:bg-indigo/5 disabled:opacity-30"
        >
          Previous
        </button>
        <span className="text-sm tabular-nums text-ink-soft">
          Page {page.number} of {pages.length}
        </span>
        {index < last ? (
          <button
            onClick={() => go(1)}
            className="rounded-full px-4 py-2 font-medium text-indigo hover:bg-indigo/5"
          >
            Next
          </button>
        ) : (
          <button
            onClick={() => {
              finishedRef.current = false;
              setIndex(0);
            }}
            className="rounded-full px-4 py-2 font-medium text-indigo hover:bg-indigo/5"
          >
            Read again
          </button>
        )}
      </div>

      <div className="mt-3 flex gap-2 overflow-x-auto pb-1" aria-label="All pages">
        {pages.map((p, i) => (
          <button
            key={p.number}
            onClick={() => {
              setIndex(i);
              setEditing(false);
            }}
            aria-label={`Go to page ${p.number}`}
            aria-current={i === index}
            className={`w-16 shrink-0 overflow-hidden rounded-sm border-2 ${
              i === index ? "border-indigo" : "border-transparent opacity-70 hover:opacity-100"
            }`}
          >
            <img src={url(p.imageUrl)} alt="" className="aspect-square w-full object-cover" />
          </button>
        ))}
      </div>

      {onFeedback && index === last && (
        <Feedback
          childName={book.childName}
          initial={book.feedback}
          prominent
          onSave={onFeedback}
        />
      )}

      <div className="mt-5 border-t border-line pt-4">
        {editing ? (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              onRedo(page.number, request);
              setEditing(false);
              setRequest("");
            }}
          >
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
              className="mt-2 w-full rounded-sm border border-line bg-sheet px-3.5 py-2.5 focus:border-indigo focus:outline-none"
            />
            <div className="mt-2 flex gap-3">
              <button className="rounded-full bg-indigo px-5 py-2 font-medium text-white hover:bg-indigo-deep">
                Rewrite page {page.number}
              </button>
              <button
                type="button"
                onClick={() => setEditing(false)}
                className="px-3 py-2 text-ink-soft hover:text-ink"
              >
                Cancel
              </button>
            </div>
            <p className="mt-2 text-sm text-ink-soft">
              Leave it empty for a fresh version of the same page.
            </p>
          </form>
        ) : (
          <button
            onClick={() => setEditing(true)}
            className="font-medium text-indigo underline decoration-indigo/30 underline-offset-4 hover:decoration-indigo"
          >
            Change page {page.number}
          </button>
        )}
      </div>

      {!!book.warnings?.length && (
        <div className="mt-5 rounded-sm bg-marigold-soft px-4 py-3 text-[0.95rem]">
          {book.warnings.map((w) => (
            <p key={w}>{w}</p>
          ))}
        </div>
      )}

      <div className="mt-6 flex flex-wrap gap-3">
        <a
          href={url(`${book.pdfUrl}&download=1`)}
          className="rounded-full bg-indigo px-6 py-2.5 font-medium text-white hover:bg-indigo-deep"
        >
          Download the book (PDF)
        </a>
        <button
          onClick={() => setShowVideo((v) => !v)}
          className="rounded-full border border-indigo/30 px-6 py-2.5 font-medium text-indigo hover:border-indigo"
        >
          {showVideo ? "Hide the read-along" : "Watch the read-along"}
        </button>
        <a
          href={url(`${book.videoUrl}&download=1`)}
          className="self-center px-2 font-medium text-indigo underline decoration-indigo/30 underline-offset-4 hover:decoration-indigo"
        >
          Download video
        </a>
      </div>
      {showVideo && (
        <>
          <video
            src={url(book.videoUrl)}
            controls
            autoPlay
            className="mt-4 w-full rounded-sm bg-ink"
          />
          <p className="mt-2 text-sm text-ink-soft">
            The video is put together when you first open it, which can take a few seconds.
          </p>
        </>
      )}

      {onFeedback && index !== last && (
        <Feedback
          childName={book.childName}
          initial={book.feedback}
          prominent={false}
          onSave={onFeedback}
        />
      )}

      <QualityReport checks={book.quality} />

      {(onReport || onDelete) && (
        <div className="mt-6 flex flex-wrap gap-x-6 gap-y-2 border-t border-line pt-4 text-sm">
          {onReport &&
            (book.reported ? (
              <span className="text-ink-soft">Reported. Thank you for telling us.</span>
            ) : (
              <button
                onClick={onReport}
                className="text-ink-soft underline decoration-line underline-offset-4 hover:text-ink"
              >
                Report a problem with this book
              </button>
            ))}
          {onDelete && (
            <button
              onClick={onDelete}
              className="text-alert underline decoration-alert/30 underline-offset-4 hover:decoration-alert"
            >
              Delete this book
            </button>
          )}
        </div>
      )}
    </div>
  );
}
