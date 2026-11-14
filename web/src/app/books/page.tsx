"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import Header from "@/components/Header";
import { api, url, type Library, type ShelfBook } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function BooksPage() {
  const { ready, me, signIn, signOut } = useAuth();
  const router = useRouter();
  const [library, setLibrary] = useState<Library | null>(null);
  const [failed, setFailed] = useState(false);

  const signedIn = !!me;
  useEffect(() => {
    if (signedIn) api.library().then(setLibrary).catch(() => setFailed(true));
  }, [signedIn]);

  return (
    <>
      <Header />
      <main className="mx-auto max-w-6xl px-5 pb-20 sm:px-8">
        <h1 className="text-4xl text-indigo sm:text-5xl">Your library</h1>

        {!ready ? null : !me ? (
          <div className="mt-6 max-w-xl">
            <p className="text-ink-soft">Sign in to see the books you&rsquo;ve made.</p>
            <button
              onClick={signIn}
              className="mt-5 rounded-full bg-indigo px-6 py-2.5 font-medium text-white hover:bg-indigo-deep"
            >
              Sign in with Google
            </button>
          </div>
        ) : failed ? (
          <p className="mt-6 text-alert">Your library couldn&rsquo;t be loaded. Please refresh.</p>
        ) : !library ? (
          <div className="h-64" aria-busy="true" />
        ) : (
          <>
            <p className="mt-2 text-ink-soft">
              {me.saved} of {me.maxSaved} books saved. {me.booksToday} of {me.booksPerDay} made
              today.
            </p>
            {library.children.length === 0 ? (
              <div className="mt-10 max-w-xl">
                <p className="text-lg">No books yet.</p>
                <Link
                  href="/#make"
                  className="mt-4 inline-block rounded-full bg-indigo px-6 py-2.5 font-medium text-white hover:bg-indigo-deep"
                >
                  Make the first one
                </Link>
              </div>
            ) : (
              library.children.map((child) => (
                <section key={child.childName} className="mt-12">
                  <h2 className="text-2xl text-indigo">For {child.childName}</h2>
                  {child.taste.summary.length > 0 && (
                    <p className="mt-1 text-ink-soft">
                      {child.childName} enjoys {child.taste.summary.join(", ")}.
                    </p>
                  )}
                  <ul className="mt-5 grid grid-cols-2 gap-x-6 gap-y-10 md:grid-cols-4">
                    {child.books.map((b) => (
                      <li key={b.id}>
                        <Shelf book={b} />
                      </li>
                    ))}
                  </ul>
                </section>
              ))
            )}
            <div className="mt-16 flex flex-wrap gap-x-8 gap-y-3 border-t border-line pt-6">
              <Link href="/#make" className="font-medium text-indigo hover:text-indigo-deep">
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
  const pct = Math.round((Math.min(book.progressPage, book.pageCount) / book.pageCount) * 100);
  return (
    <Link href={`/books/view?id=${book.id}`} className="group block">
      <img
        src={url(book.coverUrl)}
        alt=""
        className="aspect-square w-full rounded-sm bg-line object-cover shadow-[0_18px_36px_-24px_rgba(23,24,28,0.5)] transition-transform duration-300 group-hover:-translate-y-1"
      />
      <span
        className="mt-3 block font-display text-lg leading-snug text-indigo group-hover:underline"
        lang={book.language}
      >
        {book.title}
      </span>
      <span className="mt-1 block text-sm text-ink-soft">{status}</span>
      <span className="mt-1.5 block h-1 w-full overflow-hidden rounded-full bg-line" aria-hidden>
        <span className="block h-full rounded-full bg-leaf" style={{ width: `${pct}%` }} />
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
        className="text-sm text-ink-soft underline decoration-line underline-offset-4 hover:text-alert"
      >
        Delete my account and all books
      </button>
    );
  return (
    <div className="w-full max-w-xl border-l-4 border-alert bg-sheet px-5 py-4">
      <p className="font-medium">Delete your account and every book in it?</p>
      <p className="mt-1 text-ink-soft">This can&rsquo;t be undone.</p>
      <div className="mt-4 flex gap-3">
        <button
          disabled={working}
          onClick={async () => {
            setWorking(true);
            await api.deleteAccount();
            onDeleted();
          }}
          className="rounded-full bg-alert px-5 py-2 font-medium text-white disabled:opacity-50"
        >
          Delete everything
        </button>
        <button onClick={() => setAsking(false)} className="px-3 py-2 text-ink-soft hover:text-ink">
          Keep my account
        </button>
      </div>
    </div>
  );
}
