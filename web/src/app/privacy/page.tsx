import type { Metadata } from "next";
import Link from "next/link";
import { SiteFooter } from "@/components/layout/SiteFooter";
import { SiteHeader } from "@/components/layout/SiteHeader";

export const metadata: Metadata = {
  title: "Privacy policy",
  description: "How Kahaani collects, uses, stores and deletes information.",
};

const UPDATED = "14 November 2026";

export default function PrivacyPage() {
  return (
    <>
      <SiteHeader />
      <main className="page-x mx-auto w-full max-w-7xl pb-24">
        <div className="mx-auto max-w-3xl">
          <h1 className="pt-4 text-head lg:pt-8">Privacy policy</h1>
          <p className="mt-2 text-ink-soft">Last updated {UPDATED}</p>

          <div className="mt-10 space-y-10 leading-relaxed [&_h2]:mb-3 [&_h2]:text-lead [&_h2]:font-normal [&_li]:mt-1.5 [&_ul]:list-disc [&_ul]:pl-6">
            <section>
              <p>
                Kahaani makes personalised picture books for children. It is
                meant to be used by parents and guardians, not by children
                themselves. This policy explains what information Kahaani
                handles, why, who it is shared with, and how to delete it.
              </p>
            </section>

            <section>
              <h2>Information we collect</h2>
              <ul>
                <li>
                  <strong>Your Google account:</strong> your name and email
                  address, received when you sign in with Google. We never see
                  or store your Google password.
                </li>
                <li>
                  <strong>What you type about your child:</strong> a first name,
                  age, girl or boy, a short description of how they look, their
                  favourite things and the lesson you choose.
                </li>
                <li>
                  <strong>The books we make for you:</strong> the story text,
                  the pictures and the narration.
                </li>
                <li>
                  <strong>How you use your books:</strong> reading progress,
                  your ratings and feedback tags, page changes you request, and
                  reports you send.
                </li>
              </ul>
              <p className="mt-3">
                We never ask for or accept photos of children. Every picture is
                a fictional drawing made from the words you type.
              </p>
            </section>

            <section>
              <h2>How we use it</h2>
              <ul>
                <li>To write, illustrate and narrate the books you ask for.</li>
                <li>
                  To keep your books in your library so you can read them again.
                </li>
                <li>
                  To make the next story for each child closer to what they
                  enjoyed.
                </li>
                <li>
                  To check every request, story and picture for safety and
                  quality.
                </li>
                <li>To apply daily limits and prevent misuse.</li>
              </ul>
              <p className="mt-3">
                We do not sell your information, show advertising, or use it for
                any purpose other than running Kahaani.
              </p>
            </section>

            <section>
              <h2>Shared stories</h2>
              <p>
                When a new story is written, an anonymous copy is also kept with
                the child&apos;s name removed and without narration. If another
                family later asks for a very similar story, they may receive
                this copy with their own child&apos;s name. Shared copies never
                contain your name, your email or your child&apos;s name. You
                agree to this before your first book, and any parent can report
                a story to take it out of sharing.
              </p>
            </section>

            <section>
              <h2>Services that process your information</h2>
              <p>
                To make and store books, Kahaani sends information to these
                providers:
              </p>
              <ul>
                <li>
                  <strong>Google (Gemini)</strong> writes and checks the story,
                  and checks the pictures.
                </li>
                <li>
                  <strong>Groq</strong> writes the story when Gemini is
                  unavailable.
                </li>
                <li>
                  <strong>Cloudflare (Workers AI)</strong> draws the pictures
                  from an English description that never includes your
                  child&apos;s name.
                </li>
                <li>
                  <strong>Microsoft (Edge text-to-speech)</strong> records the
                  narration.
                </li>
                <li>
                  <strong>Supabase</strong> handles Google sign-in and stores
                  your account and books.
                </li>
                <li>
                  <strong>Render</strong> hosts the website and the server.
                </li>
              </ul>
              <p className="mt-3">
                These providers process the information only to provide their
                service to Kahaani.
              </p>
            </section>

            <section>
              <h2>Storage and security</h2>
              <ul>
                <li>Only you can open your books after signing in.</li>
                <li>
                  Pictures and downloads are delivered through private links
                  that expire after an hour.
                </li>
                <li>
                  Our server logs record timings and error types, never names or
                  story text.
                </li>
                <li>
                  A book that is started but not finished is kept in memory for
                  at most an hour and is never saved.
                </li>
              </ul>
            </section>

            <section>
              <h2>How long we keep it, and deleting it</h2>
              <p>
                Your books stay in your library until you delete them. You can
                delete any book from its page, or delete your account and
                everything in it from{" "}
                <Link
                  href="/books/"
                  className="text-ink underline underline-offset-4"
                >
                  your library
                </Link>
                . Deleting your account removes your sign-in, your books, your
                children&apos;s names and your feedback. Anonymous shared
                copies, which contain no names, may remain.
              </p>
            </section>

            <section>
              <h2>Children</h2>
              <p>
                Kahaani is for parents and guardians. Accounts must be created
                by an adult, who gives consent before the first book is made.
                Children should not create accounts.
              </p>
            </section>

            <section>
              <h2>Changes and contact</h2>
              <p>
                If this policy changes, the date at the top will change too. For
                questions or requests about your information, please open an
                issue on{" "}
                <a
                  href="https://github.com/LakshayJ17/kahaani/issues"
                  className="text-ink underline underline-offset-4"
                >
                  Kahaani&apos;s GitHub page
                </a>
                .
              </p>
            </section>
          </div>
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
