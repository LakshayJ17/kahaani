"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  RequestError,
  type ApiError,
  type BriefInput,
  type Child,
  type Job,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import BriefForm from "./BriefForm";
import Consent from "./Consent";
import HeroApproval from "./HeroApproval";
import Progress from "./Progress";

const STORAGE_KEY = "kahaani-job";

export default function Maker() {
  const { ready, me, available, signIn } = useAuth();
  const router = useRouter();
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [sending, setSending] = useState(false);
  const [existing, setExisting] = useState<{ id: string; title: string } | null>(null);
  const [lastBrief, setLastBrief] = useState<BriefInput | null>(null);
  const [kids, setKids] = useState<Child[]>([]);
  const stageRef = useRef<HTMLDivElement>(null);

  const remember = (j: Job | null) => {
    try {
      if (j) sessionStorage.setItem(STORAGE_KEY, j.id);
      else sessionStorage.removeItem(STORAGE_KEY);
    } catch {
      // Private browsing: just don't remember.
    }
  };

  const accept = useCallback(
    (j: Job) => {
      if (j.stage === "saved" && j.bookId) {
        remember(null);
        router.push(`/books/view?id=${j.bookId}&new=1`);
        return;
      }
      setJob(j);
      setError(j.error);
    },
    [router],
  );

  // Pick up a book in progress after a refresh (jobs live for an hour on the server).
  const signedIn = !!me;
  const consented = !!me?.consent;
  useEffect(() => {
    if (consented) api.children().then(setKids).catch(() => setKids([]));
  }, [consented]);

  useEffect(() => {
    if (!signedIn) return;
    let id: string | null = null;
    try {
      id = sessionStorage.getItem(STORAGE_KEY);
    } catch {}
    if (id) api.job(id).then(accept).catch(() => remember(null));
  }, [signedIn, accept]);

  // Poll while the server is working.
  useEffect(() => {
    if (!job?.busy) return;
    const timer = setInterval(() => {
      api
        .job(job.id)
        .then(accept)
        .catch((e: RequestError) => {
          setError(e.detail);
          setJob(null);
          remember(null);
        });
    }, 1000);
    return () => clearInterval(timer);
  }, [job?.busy, job?.id, accept]);

  const run = async (action: () => Promise<Job>) => {
    setSending(true);
    setError(null);
    try {
      const j = await action();
      accept(j);
      remember(j);
      stageRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (e) {
      setError((e as RequestError).detail);
    } finally {
      setSending(false);
    }
  };

  const create = async (brief: BriefInput, fresh = false) => {
    setLastBrief(brief);
    setExisting(null);
    setSending(true);
    setError(null);
    try {
      const res = await api.create(brief, fresh);
      if ("existingBookId" in res) {
        setExisting({ id: res.existingBookId, title: res.title });
      } else {
        accept(res);
        remember(res);
      }
      stageRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (e) {
      setError((e as RequestError).detail);
    } finally {
      setSending(false);
    }
  };

  const startOver = () => {
    setJob(null);
    setError(null);
    setExisting(null);
    remember(null);
  };

  if (!ready) return <div className="h-96" aria-busy="true" />;

  if (!me) {
    return (
      <div className="max-w-xl">
        <p className="text-lg">
          Sign in with your Google account to make a book. Your books are saved to your own
          library, so you can read them again on any device and pick up where you left off.
        </p>
        {available ? (
          <button
            onClick={signIn}
            className="mt-6 rounded-full bg-indigo px-7 py-3 font-medium text-white hover:bg-indigo-deep"
          >
            Sign in with Google
          </button>
        ) : (
          <p className="mt-6 text-ink-soft">
            Sign-in isn&rsquo;t set up on this server yet, so only the sample books are
            available.
          </p>
        )}
      </div>
    );
  }

  if (!me.consent) return <Consent />;

  const busy = sending || !!job?.busy;
  const fields = error?.fields ?? {};
  const focused = !!job && (job.busy || job.stage !== "new");

  return (
    <div
      className={
        focused
          ? "mx-auto max-w-4xl"
          : "grid gap-12 lg:grid-cols-[minmax(0,26rem)_minmax(0,1fr)] lg:gap-16"
      }
    >
      {!focused && (
        <div>
          <p className="mb-6 text-sm text-ink-soft">
            {me.booksToday} of {me.booksPerDay} books made today.
          </p>
          <BriefForm
            disabled={busy}
            fieldErrors={fields}
            onSubmit={(b) => create(b)}
            kids={kids}
            onForgetTaste={async (id) => {
              await api.forgetTaste(id);
              setKids(await api.children());
            }}
          />
        </div>
      )}

      <div
        ref={stageRef}
        className={`scroll-mt-8 ${focused ? "" : "lg:sticky lg:top-8 lg:self-start"}`}
      >
        {error && !Object.keys(fields).length && (
          <div role="alert" className="mb-6 border-l-4 border-alert bg-sheet px-5 py-4">
            <p className="font-medium">{error.message}</p>
            {error.reasons?.map((r) => (
              <p key={r} className="mt-1 text-ink-soft">
                {r}
              </p>
            ))}
          </div>
        )}

        {existing && !job ? (
          <div className="border-l-4 border-marigold bg-sheet px-5 py-4">
            <p className="font-medium">You already have this book: {existing.title}</p>
            <p className="mt-1 text-ink-soft">
              We keep one copy of each book, so it isn&rsquo;t made twice.
            </p>
            <div className="mt-4 flex flex-wrap gap-3">
              <button
                onClick={() => router.push(`/books/view?id=${existing.id}`)}
                className="rounded-full bg-indigo px-5 py-2 font-medium text-white hover:bg-indigo-deep"
              >
                Open it
              </button>
              <button
                onClick={() => lastBrief && create(lastBrief, true)}
                className="rounded-full border border-indigo/30 px-5 py-2 font-medium text-indigo hover:border-indigo"
              >
                Write a new version
              </button>
            </div>
          </div>
        ) : job?.busy ? (
          <div className="max-w-xl">
            <Progress job={job} />
          </div>
        ) : job?.stage === "hero" ? (
          <HeroApproval
            job={job}
            onApprove={() => run(() => api.approve(job.id))}
            onRetry={() => run(() => api.newHero(job.id))}
          />
        ) : (
          <Waiting />
        )}

        {job && !job.busy && job.stage !== "new" && (
          <button
            onClick={startOver}
            className="mt-8 text-ink-soft underline decoration-line underline-offset-4 hover:text-ink"
          >
            Start a new book
          </button>
        )}
      </div>
    </div>
  );
}

function Waiting() {
  return (
    <div>
      <h3 className="text-2xl text-indigo">What happens next</h3>
      <ol className="mt-5 space-y-5">
        {[
          [
            "We write the story",
            "A short tale at your child's reading level, with them as the hero and the lesson you chose.",
          ],
          [
            "You approve the hero",
            "We draw your child from your description. Try another picture until it feels right.",
          ],
          [
            "We draw every page from that picture",
            "So your child looks the same from the first page to the last.",
          ],
          [
            "It goes into your library",
            "Read it any time, change any page, and download the PDF and the narrated video.",
          ],
        ].map(([title, body], i) => (
          <li key={title} className="grid grid-cols-[2rem_1fr]">
            <span className="font-display text-2xl leading-none text-marigold">{i + 1}</span>
            <div>
              <p className="font-medium">{title}</p>
              <p className="text-ink-soft">{body}</p>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
