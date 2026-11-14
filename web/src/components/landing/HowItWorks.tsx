import { BookOpen, Brush, UserRound } from "lucide-react";
import { Reveal } from "@/components/ui/Reveal";

const STEPS = [
  {
    icon: UserRound,
    title: "You describe your child",
    body: "Their name, age, how they look and what they love. Then pick a lesson, a language and an art style.",
    time: "About a minute",
  },
  {
    icon: Brush,
    title: "We write and draw it",
    body: "A story at their reading level. You approve the hero, and every page is drawn from that picture.",
    time: "About a minute",
  },
  {
    icon: BookOpen,
    title: "You read it together",
    body: "Turn the pages on screen, play the narrated read-along video, or print the PDF.",
    time: "Every bedtime",
  },
];

export function HowItWorks() {
  return (
    <section
      aria-labelledby="how-title"
      className="page-x mx-auto max-w-7xl py-16 lg:py-24"
    >
      <Reveal>
        <h2 id="how-title" className="text-head">
          How a book is made
        </h2>
        <ol className="mt-10 grid gap-6 md:grid-cols-3">
          {STEPS.map(({ icon: Icon, title, body, time }, i) => (
            <li
              key={title}
              className="paper relative rounded-2xl p-7 transition-transform duration-300 ease-out hover:-translate-y-1"
            >
              <span
                aria-hidden="true"
                className="flex size-11 items-center justify-center rounded-full bg-saffron font-display text-lead font-bold"
              >
                {i + 1}
              </span>
              <h3 className="mt-5 text-lead">{title}</h3>
              <p className="mt-2 text-ink-soft">{body}</p>
              <p className="mt-5 inline-flex items-center gap-2 text-small font-medium">
                <Icon
                  className="size-4"
                  strokeWidth={1.75}
                  aria-hidden="true"
                />
                {time}
              </p>
            </li>
          ))}
        </ol>
      </Reveal>
    </section>
  );
}
