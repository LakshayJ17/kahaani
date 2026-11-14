"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import { SiteFooter } from "@/components/layout/SiteFooter";
import { SiteHeader } from "@/components/layout/SiteHeader";
import { Button, ButtonLink } from "@/components/ui/Button";
import { Loading } from "@/components/ui/Loading";
import { api, url, type Library, type ShelfBook } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function BooksPage() {
  const { ready, me, signIn, signOut, signingIn } = useAuth();
  const router = useRouter();
  const [library, setLibrary] = useState<Library | null>(null);
  const [failed, setFailed] = useState(false);

  const signedIn = !!me;
  useEffect(() => {
    if (signedIn)
      api
        .library()
        .then(setLibrary)
        .catch(() => setFailed(true));
  }, [signedIn]);

  return (
    <>
      <SiteHeader />
      <main className="page-x mx-auto w-full max-w-7xl pb-24">
        <h1 className="pt-4 text-head lg:pt-8">Your library</h1>

        {!ready ? (
          <Loading
            label={signingIn ? "Signing you in" : "Opening your library"}
          />
        ) : !me ? (
          <div className="mt-6 max-w-xl">
            <p className="text-ink-soft">
              Sign in to see the books you&rsquo;ve made.
            </p>
            <Button
              className="mt-5"
              onClick={() => signIn("/books/")}
              loading={signingIn}
              loadingText="Opening Google…"
            >
              Sign in with Google
            </Button>
          </div>
        ) : failed ? (
          <p className="mt-6 text-danger">
            Your library couldn&rsquo;t be loaded. Please refresh.
          </p>
        ) : !library ? (
          <Loading label="Opening your library" />
        ) : (
          <>
            <p className="mt-2 text-ink-soft">
              {me.saved} of {me.maxSaved} books saved. {me.booksToday} of{" "}
              {me.booksPerDay} made today.
            </p>
            {library.children.length === 0 ? (
              <div className="mt-10 max-w-xl">
                <p className="text-lg">No books yet.</p>
                <ButtonLink href="/create/" className="mt-4">
                  Make the first one
                </ButtonLink>
              </div>
            ) : (
              library.children.map((child) => (
                <motion.section
                  key={child.childName}
                  className="mt-14"
                  initial={{ opacity: 0, y: 24 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.7 }}
                >
                  <h2 className="text-lead font-normal">
                    For {child.childName}
                  </h2>
                  {child.taste.summary.length > 0 && (
                    <p className="mt-1 text-ink-soft">
                      {child.childName} enjoys {child.taste.summary.join(", ")}.
                    </p>
                  )}
                  <ul className="mt-6 grid grid-cols-2 items-end gap-x-6 gap-y-12 px-2 md:grid-cols-4">
                    {child.books.map((b) => (
                      <li key={b.id}>
                        <Shelf book={b} />
                      </li>
                    ))}
                  </ul>
                </motion.section>
              ))
            )}
            <div className="mt-16 flex flex-wrap gap-x-8 gap-y-3 border-t border-ink/15 pt-6">
              <Link
                href="/create/"
                className="font-medium text-ink hover:text-saffron-deep"
              >
                Make another book
              </Link>
              <DeleteAccount
                onDeleted={async () => {
                  await signOut();
                  router.push("/");
                }}
              />
            </div>
          </>
        )}
      </main>
      <SiteFooter />
    </>
  );
}

function Shelf({ book }: { book: ShelfBook }) {
  const done = book.progressPage >= book.pageCount;
  const status =
    book.readCount > 0
      ? `Read ${book.readCount === 1 ? "once" : `${book.readCount} times`}`
      : book.progressPage === 0
        ? "Not started"
        : done
          ? "Finished"
          : `Page ${book.progressPage} of ${book.pageCount}`;
  const pct = Math.round(
    (Math.min(book.progressPage, book.pageCount) / book.pageCount) * 100,
  );
  return (
    <Link href={`/books/view?id=${book.id}`} className="group block">
      <span className="relative block overflow-hidden rounded-l-sm rounded-r-xl bg-sand shadow-book transition-transform duration-300 ease-out group-hover:-translate-y-2">
        <span
          className="absolute inset-y-0 left-0 z-10 w-2.5 bg-black/12"
          aria-hidden="true"
        />
        <img
          src={url(book.coverUrl)}
          alt=""
          className="aspect-square w-full object-cover"
        />
      </span>
      <span
        className="-mx-3 mt-0 block h-3 bg-shelf shadow-[0_8px_14px_-6px_rgb(43_33_24_/_0.55)]"
        aria-hidden="true"
      />
      <span className="mt-3 block text-lead leading-snug" lang={book.language}>
        {book.title}
      </span>
      <span className="mt-1 block text-sm text-ink-soft">{status}</span>
      <span
        className="mt-2 block h-1 w-full overflow-hidden rounded-full bg-sand"
        aria-hidden
      >
        <span
          className="block h-full rounded-full bg-success transition-[width] duration-700"
          style={{ width: `${pct}%` }}
        />
      </span>
    </Link>
  );
}

function DeleteAccount({ onDeleted }: { onDeleted: () => void }) {
  const [asking, setAsking] = useState(false);
  const [working, setWorking] = useState(false);
  if (!asking)
    return (
      <button
        onClick={() => setAsking(true)}
        className="text-sm text-ink-soft underline decoration-ink/30 underline-offset-4 hover:text-danger"
      >
        Delete my account and all books
      </button>
    );
  return (
    <div className="w-full max-w-xl border-l-4 border-danger bg-page px-5 py-4">
      <p className="font-medium">Delete your account and every book in it?</p>
      <p className="mt-1 text-ink-soft">This can&rsquo;t be undone.</p>
      <div className="mt-4 flex gap-3">
        <button
          disabled={working}
          aria-busy={working || undefined}
          onClick={async () => {
            setWorking(true);
            try {
              await api.deleteAccount();
              onDeleted();
            } catch {
              setWorking(false);
            }
          }}
          className="inline-flex items-center gap-2 rounded-full bg-danger px-5 py-2 font-medium text-white disabled:opacity-70"
        >
          {working && <span className="btn-spinner" aria-hidden="true" />}
          {working ? "Deleting…" : "Delete everything"}
        </button>
        <button
          onClick={() => setAsking(false)}
          className="px-3 py-2 text-ink-soft hover:text-ink"
        >
          Keep my account
        </button>
      </div>
    </div>
  );
}
