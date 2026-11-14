import Link from "next/link";
import { ButtonLink } from "@/components/ui/Button";
import { Reveal } from "@/components/ui/Reveal";

const POINTS = [
  {
    title: "No photos, ever",
    body: "You describe your child in words. Every picture is a fictional drawing made from them.",
  },
  {
    title: "Private to you",
    body: "Your books open only for you. Delete a book, or everything, whenever you like.",
  },
  {
    title: "Kind to every family",
    body: "Every request, story and picture is checked so nothing is scary, unkind or hurtful to anyone.",
  },
];

export function ParentNote() {
  return (
    <section
      aria-labelledby="note-title"
      className="page-x mx-auto max-w-7xl py-16 lg:py-24"
    >
      <Reveal className="grid gap-10 lg:grid-cols-[1fr_1.4fr]">
        <div>
          <h2 id="note-title" className="text-head">
            A note for parents
          </h2>
          <p className="mt-4 text-ink-soft">
            Kahaani is made by AI, so please read each book before sharing it.{" "}
            <Link
              href="/privacy/"
              className="font-medium text-ink underline decoration-ink/30 underline-offset-4 hover:decoration-ink"
            >
              Read the privacy policy
            </Link>
            .
          </p>
        </div>
        <ul className="grid gap-4">
          {POINTS.map((p) => (
            <li key={p.title} className="paper rounded-2xl px-6 py-5">
              <h3 className="text-lead">{p.title}</h3>
              <p className="mt-1 text-ink-soft">{p.body}</p>
            </li>
          ))}
        </ul>
      </Reveal>

      <Reveal className="mt-20 flex flex-col items-center text-center">
        <h2 className="text-head">Tonight&rsquo;s story is a minute away</h2>
        <ButtonLink href="/create/" className="mt-6">
          Make a book
        </ButtonLink>
      </Reveal>
    </section>
  );
}
