"use client";

import Link from "next/link";
import { useAuth } from "@/lib/auth";

export default function Header({ home = false }: { home?: boolean }) {
  const { ready, me, available, signIn, signOut } = useAuth();
  return (
    <header className="mx-auto flex max-w-6xl flex-wrap items-baseline justify-between gap-3 px-5 py-6 sm:px-8">
      <Link href="/" className="font-display text-2xl text-indigo">
        Kahaani
      </Link>
      <nav className="flex flex-wrap items-baseline gap-x-6 gap-y-2 text-[0.95rem] text-ink-soft">
        {home && (
          <a href="#samples" className="hover:text-ink">
            Sample books
          </a>
        )}
        {ready && me && (
          <Link href="/books" className="font-medium text-indigo hover:text-indigo-deep">
            My books
          </Link>
        )}
        {ready &&
          available &&
          (me ? (
            <button onClick={signOut} className="hover:text-ink">
              Sign out
            </button>
          ) : (
            <button onClick={signIn} className="font-medium text-indigo hover:text-indigo-deep">
              Sign in with Google
            </button>
          ))}
      </nav>
    </header>
  );
}
