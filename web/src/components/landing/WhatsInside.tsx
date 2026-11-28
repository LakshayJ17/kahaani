import {
  BookHeart,
  Languages,
  PencilLine,
  PlayCircle,
  Sprout,
  UserRound,
} from "lucide-react";
import { Reveal } from "@/components/ui/Reveal";

const ITEMS = [
  {
    icon: UserRound,
    title: "Your child on every page",
    body: "Approve the hero once and they look the same from the first page to the last.",
  },
  {
    icon: Languages,
    title: "Hindi or English",
    body: "Natural sentences at their reading level, with Hindi letters printed correctly.",
  },
  {
    icon: PlayCircle,
    title: "A read-along video",
    body: "Each page stays on screen as long as it is read aloud, so little ones can follow.",
  },
  {
    icon: PencilLine,
    title: "Change any page",
    body: "Ask for a funnier page or add the grandmother. Only that page changes.",
  },
  {
    icon: BookHeart,
    title: "Stories that learn",
    body: "Tell us how each book went, and the next one for that child follows what they loved.",
  },
  {
    icon: Sprout,
    title: "A gentle lesson",
    body: "Sharing, bravery, honesty, kindness, new food, bedtime, or one of your own.",
  },
];

export function WhatsInside() {
  return (
    <section
      aria-labelledby="inside-title"
      className="page-x mx-auto max-w-7xl py-16 lg:py-24"
    >
      <Reveal className="paper rounded-[22px] px-6 py-12 sm:px-12 lg:px-16">
        <h2 id="inside-title" className="text-head">
          What&apos;s inside every book
        </h2>
        <ul className="mt-10 grid gap-x-12 gap-y-9 sm:grid-cols-2 lg:grid-cols-3">
          {ITEMS.map(({ icon: Icon, title, body }) => (
            <li key={title} className="flex gap-4">
              <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-saffron-soft">
                <Icon
                  className="size-5"
                  strokeWidth={1.75}
                  aria-hidden="true"
                />
              </span>
              <div>
                <h3 className="font-display text-lead">{title}</h3>
                <p className="mt-1 text-ink-soft">{body}</p>
              </div>
            </li>
          ))}
        </ul>
      </Reveal>
    </section>
  );
}
