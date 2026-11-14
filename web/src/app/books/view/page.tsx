"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import BookReader from "@/components/BookReader";
import Header from "@/components/Header";
import Progress from "@/components/Progress";
import { api, RequestError, type ApiError, type Job, type SavedBook } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function ViewPage() {
  return (
    <>
      <Header />
      <main className="mx-auto max-w-4xl px-5 pb-20 sm:px-8">
        {/* useSearchParams needs a Suspense boundary in a static export. */}
        <Suspense fallback={<div className="h-96" aria-busy="true" />}>
          <View />
        </Suspense>
      </main>
    </>
  );
}

function View() {
  const params = useSearchParams();
  const id = params.get("id") ?? "";
  const isNew = params.get("new") === "1";
  const router = useRouter();
  const { ready, me, signIn, refresh } = useAuth();
  const [book, setBook] = useState<SavedBook | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const load = useCallback(() => {
    api
      .book(id)
      .then((b) => {
        setBook(b);
        setJob(b.job?.busy ? b.job : null);
        if (b.job?.error) setError(b.job.error);
      })
      .catch((e: RequestError) => setError(e.detail));
  }, [id]);

  const signedIn = !!me;
  useEffect(() => {
    if (signedIn && id) load();
  }, [signedIn, id, load]);

  // Update today's count once after a new book (refreshing `me` must not reload the book).
  const counted = useRef(false);
  useEffect(() => {
    if (isNew && signedIn && !counted.current) {
      counted.current = true;
      refresh();
    }
  }, [isNew, signedIn, refresh]);

  // While a page is being rewritten, poll; reload the book when it's done.
  useEffect(() => {
    if (!job?.busy) return;
    const t = setInterval(() => {
      api.job(job.id).then((j) => {
        setJob(j);
        if (!j.busy) {
          if (j.error) setError(j.error);
          load();
        }
      });
    }, 1000);
    return () => clearInterval(t);
  }, [job?.busy, job?.id, load]);

  if (!ready) return null;
  if (!me)
    return (
      <div className="max-w-xl">
        <p className="text-ink-soft">Sign in to open this book.</p>
        <button
          onClick={signIn}
          className="mt-5 rounded-full bg-indigo px-6 py-2.5 font-medium text-white hover:bg-indigo-deep"
        >
          Sign in with Google
        </button>
      </div>
    );

  return (
    <>
      <p className="mb-6 text-sm">
        <Link href="/books" className="text-indigo underline decoration-indigo/30 underline-offset-4">
          Back to your library
        </Link>
      </p>
      {isNew && book && !job && (
        <p className="mb-6 rounded-sm bg-mood-calm px-4 py-3">
          Your book is ready and saved to your library.
        </p>
      )}
      {error && (
        <div role="alert" className="mb-6 border-l-4 border-alert bg-sheet px-5 py-4">
          <p className="font-medium">{error.message}</p>
          {error.reasons?.map((r) => (
            <p key={r} className="mt-1 text-ink-soft">
              {r}
            </p>
          ))}
        </div>
      )}
      {job?.busy ? (
        <div className="max-w-xl">
          <Progress job={job} />
        </div>
      ) : book ? (
        <>
          <BookReader
            book={book}
            onRedo={async (n, request) => {
              setError(null);
              try {
                setJob(await api.redo(book.id, n, request));
              } catch (e) {
                setError((e as RequestError).detail);
              }
            }}
            onPage={(page, finished) => {
              api.progress(book.id, page, finished).catch(() => {});
            }}
            onReport={async () => {
              await api.report(book.id);
              setBook({ ...book, reported: true });
            }}
            onDelete={() => setConfirmDelete(true)}
            onFeedback={async (fb) => {
              const res = await api.feedback(book.id, fb);
              setBook({ ...book, feedback: fb });
              return res.taste;
            }}
          />
          {confirmDelete && (
            <div className="mt-6 border-l-4 border-alert bg-sheet px-5 py-4">
              <p className="font-medium">Delete this book? This can&rsquo;t be undone.</p>
              <div className="mt-3 flex gap-3">
                <button
                  onClick={async () => {
                    await api.deleteBook(book.id);
                    router.push("/books");
                  }}
                  className="rounded-full bg-alert px-5 py-2 font-medium text-white"
                >
                  Delete
                </button>
                <button
                  onClick={() => setConfirmDelete(false)}
                  className="px-3 py-2 text-ink-soft hover:text-ink"
                >
                  Keep it
                </button>
              </div>
            </div>
          )}
        </>
      ) : !error ? (
        <div className="h-96" aria-busy="true" />
      ) : null}
    </>
  );
}
