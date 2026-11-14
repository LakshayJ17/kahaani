import Link from "next/link";
import Header from "@/components/Header";
import Maker from "@/components/Maker";
import Samples from "@/components/Samples";

export default function Home() {
  return (
    <>
      <Header home />

      <main>
        <section className="mx-auto grid max-w-6xl items-center gap-10 px-5 pb-16 pt-6 sm:px-8 lg:grid-cols-[1fr_1.15fr] lg:gap-14 lg:pb-24 lg:pt-10">
          <div>
            <h1 className="text-[2.6rem] text-indigo sm:text-6xl">
              A bedtime story where your child is the hero
            </h1>
            <p className="mt-5 max-w-[34rem] text-lg text-ink-soft">
              Tell us a little about them. In about a minute you get an illustrated book in
              Hindi or English, a narrated read-along video, and a story with a gentle
              lesson you choose. It&rsquo;s free.
            </p>
            <a
              href="#make"
              className="mt-8 inline-block rounded-full bg-indigo px-7 py-3 font-medium text-white hover:bg-indigo-deep"
            >
              Make a book
            </a>
          </div>

          <figure>
            <img
              src="/img/spread-fatima.jpg"
              alt="A page from a sample book: Fatima in a blue headscarf reads on a balcony under the stars, with her toy owl."
              className="w-full rounded-sm shadow-[0_30px_60px_-30px_rgba(24,34,67,0.55)]"
            />
            <figcaption className="mt-3 text-sm text-ink-soft">
              Page one of <em>Fatima and the Big Night Sky</em>, made for a seven-year-old.
            </figcaption>
          </figure>
        </section>

        <section id="make" className="scroll-mt-4 bg-sheet py-16 lg:py-24">
          <div className="mx-auto max-w-6xl px-5 sm:px-8">
            <h2 className="text-4xl text-indigo">Make a book</h2>
            <p className="mt-2 max-w-[38rem] text-ink-soft">
              Describe your child in words. Every book is saved to your own library.
            </p>
            <div className="mt-10">
              <Maker />
            </div>
          </div>
        </section>

        <section id="samples" className="mx-auto max-w-6xl scroll-mt-4 px-5 py-16 sm:px-8 lg:py-24">
          <h2 className="text-4xl text-indigo">Sample books</h2>
          <p className="mt-2 max-w-[38rem] text-ink-soft">
            Four books made with Kahaani. Open one to watch the read-along.
          </p>
          <div className="mt-10">
            <Samples />
          </div>
          <figure className="mt-16 max-w-3xl">
            <img
              src="/img/spread-kavya-hi.jpg"
              alt="A Hindi page from a sample book: Kavya in a yellow raincoat folds paper boats by a rainy window, with her toy frog, drawn in Indian folk art style."
              className="w-full rounded-sm shadow-[0_24px_50px_-30px_rgba(24,34,67,0.5)]"
            />
            <figcaption className="mt-3 text-sm text-ink-soft" lang="hi">
              <span lang="en">A page from </span>काव्या और कागज़ की नाव
              <span lang="en">, in Hindi, for a six-year-old.</span>
            </figcaption>
          </figure>
        </section>

        <section id="privacy" className="scroll-mt-4 bg-indigo py-16 text-white lg:py-20">
          <div className="mx-auto grid max-w-6xl gap-10 px-5 sm:px-8 lg:grid-cols-[1fr_1.4fr]">
            <h2 className="text-4xl">Your child&rsquo;s details stay yours</h2>
            <div className="space-y-4 text-white/85">
              <p>
                There are no photos. You describe your child in words, and every picture is a
                fictional drawing made from that description.
              </p>
              <p>
                Your books are saved to your library, which only you can open after signing in
                with Google. You can delete a book, or your account and everything in it, at
                any time.
              </p>
              <p>
                To make books faster, each new story is also kept with the child&rsquo;s name
                removed, and may be reused for another family who asks for a very similar
                story. You agree to this before your first book, and any parent can report a
                book to take it out of sharing.
              </p>
              <p>
                Every request and every book is checked for safety and quality before you see
                it. The stories and pictures are made by AI, so please read the book before
                sharing it with your child.
              </p>
              <p className="text-white/65">
                The story is written by Google Gemini, the pictures are drawn by Cloudflare
                Workers AI, and the narration uses Microsoft Edge&rsquo;s voices. Accounts and
                books are stored with Supabase.
              </p>
            </div>
          </div>
        </section>
      </main>

      <footer className="mx-auto flex max-w-6xl flex-wrap justify-between gap-3 px-5 py-8 text-sm text-ink-soft sm:px-8">
        <span>
          Kahaani makes picture books with AI. Read before you share.{" "}
          <Link href="/privacy/" className="underline decoration-line underline-offset-4 hover:text-ink">
            Privacy policy
          </Link>
        </span>
        <span>Three books per family per day.</span>
      </footer>
    </>
  );
}
