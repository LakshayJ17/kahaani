"use client";

import { AnimatePresence, motion } from "framer-motion";
import { RefreshCw } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Loading } from "@/components/ui/Loading";
import {
  api,
  RequestError,
  url,
  type ApiError,
  type BriefInput,
  type Child,
  type Job,
  type Style,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import BriefForm from "./BriefForm";
import Consent from "./Consent";
import Progress from "./Progress";

const STORAGE_KEY = "kahaani-job";
const STYLE_NAMES: Record<Style, string> = {
  watercolour: "watercolour",
  cartoon: "cartoon",
  folk: "Indian folk art",
};

/**
 * The book studio: a large picture canvas on the left (a preview of the chosen style, the
 * hero being drawn, then the hero itself) and a rail on the right with the form, the progress
 * steps or the hero approval.
 */
export default function Studio() {
  const { ready, me, available, signIn, signingIn } = useAuth();
  const router = useRouter();
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [sending, setSending] = useState(false);
  // Which button started the current request, so only that one shows a spinner.
  const [pending, setPending] = useState<
    "create" | "fresh" | "approve" | "hero" | null
  >(null);
  const [existing, setExisting] = useState<{
    id: string;
    title: string;
  } | null>(null);
  const [lastBrief, setLastBrief] = useState<BriefInput | null>(null);
  const [kids, setKids] = useState<Child[]>([]);
  const [style, setStyle] = useState<Style>("watercolour");
  const railRef = useRef<HTMLDivElement>(null);

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
        router.push(`/books/view/?id=${j.bookId}&new=1`);
        return;
      }
      setJob(j);
      setError(j.error);
    },
    [router],
  );

  const signedIn = !!me;
  const consented = !!me?.consent;
  useEffect(() => {
    if (consented)
      api
        .children()
        .then(setKids)
        .catch(() => setKids([]));
  }, [consented]);

  // Pick up a book in progress after a refresh (jobs live for an hour on the server).
  useEffect(() => {
    if (!signedIn) return;
    let id: string | null = null;
    try {
      id = sessionStorage.getItem(STORAGE_KEY);
    } catch {}
    if (id)
      api
        .job(id)
        .then(accept)
        .catch(() => remember(null));
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

  const scrollToRail = () => {
    if (window.innerWidth < 1024)
      railRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  const run = async (action: () => Promise<Job>, which: "approve" | "hero") => {
    setSending(true);
    setPending(which);
    setError(null);
    try {
      const j = await action();
      accept(j);
      remember(j);
      scrollToRail();
    } catch (e) {
      setError((e as RequestError).detail);
    } finally {
      setSending(false);
      setPending(null);
    }
  };

  const create = async (brief: BriefInput, fresh = false) => {
    setLastBrief(brief);
    setExisting(null);
    setSending(true);
    setPending(fresh ? "fresh" : "create");
    setError(null);
    try {
      const res = await api.create(brief, fresh);
      if ("existingBookId" in res)
        setExisting({ id: res.existingBookId, title: res.title });
      else {
        accept(res);
        remember(res);
      }
      scrollToRail();
    } catch (e) {
      setError((e as RequestError).detail);
    } finally {
      setSending(false);
      setPending(null);
    }
  };

  const startOver = () => {
    setJob(null);
    setError(null);
    setExisting(null);
    remember(null);
  };

  const busy = sending || !!job?.busy;
  const fields = error?.fields ?? {};
  const heroUrl = job?.heroUrl ? url(job.heroUrl) : null;
  const stage: "preview" | "working" | "hero" = job?.busy
    ? "working"
    : job?.stage === "hero"
      ? "hero"
      : "preview";

  // A new stage changes the picture: bring the top of the studio back into view.
  useEffect(() => {
    if (stage !== "preview") window.scrollTo({ top: 0, behavior: "smooth" });
  }, [stage]);

  const heading =
    stage === "hero"
      ? "Is this your hero?"
      : stage === "working"
        ? "Making your book"
        : "Make a book";

  return (
    <>
      <AnimatePresence mode="wait" initial={false}>
        <motion.h1
          key={heading}
          className="pt-4 text-head lg:pt-8"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
        >
          {heading}
        </motion.h1>
      </AnimatePresence>

      <div className="mt-8 grid gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,24rem)] lg:gap-14 xl:grid-cols-[minmax(0,1fr)_minmax(0,28rem)]">
        {/* The book's cover, taking shape as the book is made. */}
        <section aria-label="Your book" className="lg:order-2">
          <div className="lg:sticky lg:top-6">
            <motion.div
              className="page-edges relative mx-auto max-w-sm lg:max-w-none"
              initial={false}
              animate={{ rotate: stage === "working" ? 0 : -1.2 }}
              transition={{ type: "spring", stiffness: 120, damping: 18 }}
            >
              <div className="closed-book overflow-hidden bg-page">
                <div className="relative aspect-square overflow-hidden bg-sand">
                  <AnimatePresence initial={false} mode="popLayout">
                    <motion.img
                      key={
                        stage !== "preview" && heroUrl
                          ? heroUrl
                          : `style-${style}`
                      }
                      src={
                        stage !== "preview" && heroUrl
                          ? heroUrl
                          : `/img/hero-${style}.jpg`
                      }
                      alt={
                        stage === "hero"
                          ? "Your hero, drawn from your description"
                          : `A sample cover in ${STYLE_NAMES[style]}`
                      }
                      className="absolute inset-0 size-full object-cover"
                      style={{ transformOrigin: "left center" }}
                      initial={{ rotateY: 60, opacity: 0 }}
                      animate={{ rotateY: 0, opacity: 1 }}
                      exit={{ opacity: 0 }}
                      transition={{ duration: 0.6, ease: [0.22, 0.8, 0.24, 1] }}
                    />
                  </AnimatePresence>
                  {stage === "working" && (
                    <div
                      aria-hidden="true"
                      className="lamp-glow pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_50%_30%,rgb(255_214_140/0.9),transparent_65%)]"
                    />
                  )}
                </div>
                <div className="border-t border-ink/10 px-5 py-4">
                  <p
                    className="font-display text-lead leading-snug"
                    lang={job?.language}
                  >
                    {job?.title ??
                      (stage === "working"
                        ? "Writing your story..."
                        : "Your child's book")}
                  </p>
                  <p className="text-small text-ink-soft">
                    {job?.forLine ?? `Pictures in ${STYLE_NAMES[style]}`}
                  </p>
                </div>
              </div>
            </motion.div>
            <p
              className="mt-5 text-center text-small text-ink-soft"
              aria-live="polite"
            >
              {stage === "hero"
                ? "Your hero, ready for every page"
                : stage === "working"
                  ? job?.step || "Working"
                  : "Your book comes as a PDF and a narrated read-along video"}
            </p>
          </div>
        </section>

        {/* Rail */}
        <div ref={railRef} className="scroll-mt-6 lg:order-1">
          {error && !Object.keys(fields).length && (
            <motion.div
              role="alert"
              className="mb-6 rounded-2xl paper px-5 py-4"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
            >
              <p className="font-medium text-danger">{error.message}</p>
              {error.reasons?.map((r) => (
                <p key={r} className="mt-1 text-ink-soft">
                  {r}
                </p>
              ))}
            </motion.div>
          )}

          <AnimatePresence mode="wait" initial={false}>
            <motion.div
              key={
                !ready
                  ? "loading"
                  : !me
                    ? "signin"
                    : !me.consent
                      ? "consent"
                      : existing && !job
                        ? "existing"
                        : stage
              }
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
            >
              {!ready ? (
                <Loading
                  label={signingIn ? "Signing you in" : "Getting things ready"}
                />
              ) : !me ? (
                <div className="rounded-2xl paper p-6">
                  <h2 className="text-lead font-normal">
                    Sign in to make a book
                  </h2>
                  <p className="mt-2 text-body text-ink-soft">
                    Your books are saved to your own library, so you can read
                    them again on any device and pick up where you left off.
                  </p>
                  {available ? (
                    <Button
                      className="mt-6"
                      onClick={() => signIn()}
                      loading={signingIn}
                      loadingText="Opening Google..."
                    >
                      Continue with Google
                    </Button>
                  ) : (
                    <p className="mt-6 text-ink-soft">
                      Sign-in isn&apos;t set up on this server yet.
                    </p>
                  )}
                </div>
              ) : !me.consent ? (
                <Consent />
              ) : existing && !job ? (
                <div className="rounded-2xl paper p-6">
                  <h2 className="text-lead font-normal">
                    You already have this book
                  </h2>
                  <p className="mt-1 text-body">{existing.title}</p>
                  <p className="mt-2 text-small text-ink-soft">
                    We keep one copy of each book, so it isn&apos;t made twice.
                  </p>
                  <div className="mt-5 flex flex-wrap gap-3">
                    <Button
                      onClick={() =>
                        router.push(`/books/view/?id=${existing.id}`)
                      }
                      disabled={busy}
                    >
                      Open it
                    </Button>
                    <Button
                      variant="secondary"
                      onClick={() => lastBrief && create(lastBrief, true)}
                      loading={pending === "fresh"}
                      loadingText="Starting..."
                    >
                      Write a new version
                    </Button>
                  </div>
                </div>
              ) : stage === "working" && job ? (
                <Progress job={job} />
              ) : stage === "hero" && job ? (
                <div>
                  <p className="text-ink-soft">{job.forLine}</p>
                  <h2
                    className="mt-1 text-lead font-normal"
                    lang={job.language}
                  >
                    {job.title}
                  </h2>
                  <p className="mt-4 text-body text-ink-soft">
                    {job.reused === "story+pictures"
                      ? "Another family asked for a very similar story, so this checked book is reused with your child's name."
                      : job.reused === "story"
                        ? "This story was first written, and checked, for another child with a similar idea. Your child's pictures are new."
                        : "Every page is drawn from this picture, so your child looks the same throughout."}
                  </p>
                  <div className="mt-6 flex flex-col gap-3">
                    <Button
                      onClick={() => run(() => api.approve(job.id), "approve")}
                      disabled={busy}
                      loading={pending === "approve"}
                      loadingText="Starting the pages..."
                    >
                      Yes, draw the pages
                    </Button>
                    <Button
                      variant="secondary"
                      onClick={() => run(() => api.newHero(job.id), "hero")}
                      disabled={busy}
                      loading={pending === "hero"}
                      loadingText="Drawing..."
                      icon={<RefreshCw className="size-4" strokeWidth={1.5} />}
                    >
                      Another picture
                    </Button>
                  </div>
                  <button
                    onClick={startOver}
                    className="mt-6 text-small text-ink-soft underline decoration-ink/30 underline-offset-4 hover:text-ink"
                  >
                    Start again with new details
                  </button>
                </div>
              ) : (
                <>
                  <p className="mb-6 text-small text-ink-soft">
                    {me.booksToday} of {me.booksPerDay} books made today
                  </p>
                  <BriefForm
                    disabled={busy}
                    sending={pending === "create"}
                    fieldErrors={fields}
                    onSubmit={(b) => create(b)}
                    onStyleChange={setStyle}
                    kids={kids}
                    onForgetTaste={async (id) => {
                      await api.forgetTaste(id);
                      setKids(await api.children());
                    }}
                  />
                </>
              )}
            </motion.div>
          </AnimatePresence>
        </div>
      </div>
    </>
  );
}
