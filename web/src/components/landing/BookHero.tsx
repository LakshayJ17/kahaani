"use client";

import { motion } from "framer-motion";
import { BookOpen, Languages, PlayCircle } from "lucide-react";
import { useState } from "react";
import { OpenBook } from "@/components/book/OpenBook";
import { ButtonAnchor, ButtonLink } from "@/components/ui/Button";

type StyleId = "watercolour" | "cartoon" | "folk";

const STYLES: { id: StyleId; name: string; ribbon: string; caption: string }[] =
  [
    {
      id: "watercolour",
      name: "Watercolour",
      ribbon: "var(--ribbon-watercolour)",
      caption: "Watercolour, from a book made for a five-year-old",
    },
    {
      id: "cartoon",
      name: "Cartoon",
      ribbon: "var(--ribbon-cartoon)",
      caption: "Cartoon, from a book made for a four-year-old",
    },
    {
      id: "folk",
      name: "Folk art",
      ribbon: "var(--ribbon-folk)",
      caption: "Indian folk art, from a book made for a seven-year-old",
    },
  ];

const INCLUDED = [
  { icon: BookOpen, label: "Illustrated book (PDF)" },
  { icon: PlayCircle, label: "Narrated read-along video" },
  { icon: Languages, label: "Hindi or English" },
];

/** The landing hero: an open picture book. Ribbon bookmarks turn to another art style. */
export function BookHero() {
  const [active, setActive] = useState<StyleId>("watercolour");
  const [dir, setDir] = useState<1 | -1>(1);
  const index = STYLES.findIndex((s) => s.id === active);
  const current = STYLES[index];

  const choose = (id: StyleId) => {
    if (id === active) return;
    setDir(STYLES.findIndex((s) => s.id === id) > index ? 1 : -1);
    setActive(id);
  };

  const ribbons = (
    <div
      role="radiogroup"
      aria-label="Art style"
      className="absolute -top-3 right-8 z-40 flex gap-1.5 md:left-[calc(50%+14px)] md:right-auto"
    >
      {STYLES.map((s) => {
        const on = s.id === active;
        return (
          <motion.button
            key={s.id}
            type="button"
            role="radio"
            aria-checked={on}
            aria-label={`${s.name} style`}
            onClick={() => choose(s.id)}
            className="ribbon flex w-8 justify-center pt-4 text-[0.68rem] font-semibold tracking-wide text-white shadow-[1px_2px_3px_rgb(0_0_0/0.25)]"
            style={{ backgroundColor: s.ribbon, writingMode: "vertical-rl" }}
            initial={false}
            animate={{ height: on ? 150 : 96 }}
            whileHover={{ height: on ? 150 : 112 }}
            transition={{ type: "spring", stiffness: 240, damping: 22 }}
          >
            {s.name}
          </motion.button>
        );
      })}
    </div>
  );

  return (
    <section className="page-x mx-auto max-w-7xl pb-16 pt-6 lg:pb-24">
      <OpenBook
        turnKey={active}
        direction={dir}
        leftNumber={1}
        rightNumber={2}
        spine={ribbons}
        left={
          <div className="flex h-full items-center p-4 sm:p-6">
            <img
              src={`/img/hero-${active}.jpg`}
              alt={current.caption}
              className="aspect-square w-full rounded-[3px] object-cover shadow-[0_1px_2px_rgb(43_33_24/0.25)]"
            />
          </div>
        }
        right={
          <div className="flex h-full flex-col justify-center px-6 pb-14 pt-10 sm:px-10 md:pl-32 md:pr-12 lg:pl-36">
            <h1 className="max-w-[14ch] text-[clamp(2.25rem,1.4rem+2.6vw,3.75rem)] leading-[1.05]">
              A bedtime story starring your child
            </h1>
            <p className="mt-4 max-w-[30rem] text-lead text-ink-soft">
              Describe your child in a few words. In about a minute,
              they&apos;re the hero of their own picture book.
            </p>
            <ul className="mt-6 flex flex-wrap gap-2">
              {INCLUDED.map(({ icon: Icon, label }) => (
                <li
                  key={label}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-saffron-soft px-3 py-1.5 text-small font-medium"
                >
                  <Icon
                    className="size-4"
                    strokeWidth={1.75}
                    aria-hidden="true"
                  />
                  {label}
                </li>
              ))}
            </ul>
            <div className="mt-7 flex flex-wrap gap-3">
              <ButtonLink href="/create/">Make a book</ButtonLink>
              <ButtonAnchor href="#read-along" variant="secondary">
                Watch a read-along
              </ButtonAnchor>
            </div>
            <p aria-live="polite" className="mt-8 text-small text-ink-soft">
              {current.caption}. Pull a ribbon to see another style.
            </p>
          </div>
        }
      />
    </section>
  );
}
