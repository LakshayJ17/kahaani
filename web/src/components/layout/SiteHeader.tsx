"use client";

import Link from "next/link";
import { ButtonLink } from "@/components/ui/Button";
import { useAuth } from "@/lib/auth";
import { Wordmark } from "./Logo";

export function SiteHeader() {
  const { ready, me, available, signIn, signOut, signingIn } = useAuth();
  const link = "rounded-lg px-3 py-2 font-medium hover:bg-sand/70";
  return (
    <nav
      aria-label="Main"
      className="page-x mx-auto flex w-full max-w-7xl items-center justify-between gap-3 py-5"
    >
      <Link href="/" aria-label="Kahaani home" className="rounded-lg">
        <Wordmark />
      </Link>
      <ul className="flex items-center gap-1 text-small sm:gap-2">
        <li className="hidden md:block">
          <Link href="/#samples" className={link}>
            Sample books
          </Link>
        </li>
        <li className="hidden md:block">
          <Link href="/privacy/" className={link}>
            Privacy
          </Link>
        </li>
        {ready && me && (
          <li>
            <Link href="/books/" className={link}>
              My books
            </Link>
          </li>
        )}
        {ready && available && (
          <li>
            {me ? (
              <button onClick={signOut} className={link}>
                Sign out
              </button>
            ) : (
              <button
                onClick={() => signIn()}
                disabled={signingIn}
                aria-busy={signingIn || undefined}
                className={`${link} inline-flex items-center gap-2`}
              >
                {signingIn && (
                  <span className="btn-spinner" aria-hidden="true" />
                )}
                {signingIn ? "Signing in…" : "Sign in"}
              </button>
            )}
          </li>
        )}
        <li className="ml-1">
          <ButtonLink href="/create/" className="min-h-10 px-4 text-small">
            Make a book
          </ButtonLink>
        </li>
      </ul>
    </nav>
  );
}
