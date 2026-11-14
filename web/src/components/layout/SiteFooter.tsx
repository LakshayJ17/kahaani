import Link from "next/link";
import { Wordmark } from "./Logo";

export function SiteFooter() {
  return (
    <footer className="mt-auto border-t border-ink/10">
      <div className="page-x mx-auto grid max-w-7xl gap-8 py-12 md:grid-cols-[1fr_2fr]">
        <div>
          <Wordmark />
          <p className="mt-3 max-w-xs text-small text-ink-soft">
            Picture books starring your child, in Hindi and English.
          </p>
        </div>
        <div className="grid gap-6 text-small text-ink-soft sm:grid-cols-2">
          <p>
            The stories and pictures are made by AI. Please read each book
            before sharing it with your child. Children are described in words
            only; no photos are ever used.
          </p>
          <div className="flex flex-col gap-2">
            <Link
              href="/create/"
              className="font-medium text-ink hover:underline"
            >
              Make a book
            </Link>
            <Link
              href="/books/"
              className="font-medium text-ink hover:underline"
            >
              My books
            </Link>
            <Link
              href="/privacy/"
              className="font-medium text-ink hover:underline"
            >
              Privacy policy
            </Link>
          </div>
        </div>
      </div>
      <p className="page-x mx-auto max-w-7xl pb-8 text-small text-ink-soft">
        © {new Date().getFullYear()} Kahaani
      </p>
    </footer>
  );
}
