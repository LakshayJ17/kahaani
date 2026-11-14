"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";
import type { BriefInput, Child, Language, Style } from "@/lib/api";

const LESSONS: { value: string; label: string }[] = [
  { value: "sharing", label: "Sharing" },
  { value: "bravery", label: "Being brave" },
  { value: "honesty", label: "Telling the truth" },
  { value: "kindness", label: "Kindness" },
  { value: "trying new food", label: "Trying new food" },
  { value: "sleeping on time", label: "Sleeping on time" },
  { value: "custom", label: "Something else" },
];

const STYLES: { value: Style; label: string }[] = [
  { value: "watercolour", label: "Watercolour" },
  { value: "cartoon", label: "Cartoon" },
  { value: "folk", label: "Indian folk art" },
];

const AGES = [3, 4, 5, 6, 7, 8];

interface Props {
  disabled: boolean;
  fieldErrors: Record<string, string>;
  onSubmit: (brief: BriefInput) => void;
  kids?: Child[];
  onForgetTaste?: (childId: string) => Promise<void>;
  onStyleChange?: (style: Style) => void;
}

export default function BriefForm({
  disabled,
  fieldErrors,
  onSubmit,
  kids = [],
  onForgetTaste,
  onStyleChange,
}: Props) {
  const [missingHero, setMissingHero] = useState(false);
  const [kidId, setKidId] = useState<string | null>(null);
  const kid = kids.find((k) => k.id === kidId) ?? null;
  const [brief, setBrief] = useState<BriefInput>({
    child_name: "",
    age: 5,
    hero: "",
    appearance: "",
    favourites: "",
    lesson: "sharing",
    custom_lesson: "",
    language: "en",
    style: "watercolour",
    pages: 4,
    use_taste: true,
  });

  const pick = (k: Child | null) => {
    setKidId(k?.id ?? null);
    setMissingHero(false);
    if (!k) {
      setBrief((b) => ({
        ...b,
        child_name: "",
        hero: "",
        appearance: "",
        favourites: "",
      }));
      return;
    }
    const style = k.taste.style ?? k.last?.style;
    if (style) onStyleChange?.(style);
    setBrief((b) => ({
      ...b,
      child_name: k.name,
      age: k.age,
      ...(k.last ?? {}),
      style: k.taste.style ?? k.last?.style ?? b.style,
      use_taste: true,
    }));
  };
  const set = <K extends keyof BriefInput>(key: K, value: BriefInput[K]) => {
    setBrief((b) => ({ ...b, [key]: value }));
    if (key === "style") onStyleChange?.(value as Style);
  };

  return (
    <form
      className="flex flex-col gap-7"
      onSubmit={(e) => {
        e.preventDefault();
        if (!brief.hero) {
          setMissingHero(true);
          return;
        }
        setMissingHero(false);
        onSubmit(brief);
      }}
    >
      <fieldset disabled={disabled} className="contents">
        {kids.length > 0 && (
          <div role="radiogroup" aria-label="Who is this book for?">
            <p className="mb-2 font-medium">Who is this book for?</p>
            <div className="flex flex-wrap gap-2">
              {kids.map((k) => (
                <Pill
                  key={k.id}
                  selected={kidId === k.id}
                  onClick={() => pick(k)}
                >
                  {k.name}
                </Pill>
              ))}
              <Pill selected={kidId === null} onClick={() => pick(null)}>
                Someone new
              </Pill>
            </div>
          </div>
        )}

        {kid && (
          <div className="rounded-xl bg-mood-calm px-5 py-4">
            <p className="font-medium">
              What we&rsquo;ve learned about {kid.name}
            </p>
            <p className="mt-1 text-ink-soft">
              {kid.taste.summary.length
                ? `${kid.name} enjoys ${kid.taste.summary.join(", ")}.`
                : `Nothing yet. Rate ${kid.name}'s books after reading and we'll learn what ${
                    kid.name
                  } enjoys.`}
            </p>
            {kid.taste.summary.length > 0 && (
              <div className="mt-3 flex flex-wrap items-center gap-x-6 gap-y-2 text-[0.95rem]">
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={brief.use_taste !== false}
                    onChange={(e) => set("use_taste", e.target.checked)}
                    className="h-4 w-4 accent-[var(--saffron-deep)]"
                  />
                  Use this for the next story
                </label>
                {onForgetTaste && (
                  <button
                    type="button"
                    onClick={() => onForgetTaste(kid.id)}
                    className="text-ink-soft underline decoration-ink/30 underline-offset-4 hover:text-ink"
                  >
                    Forget this
                  </button>
                )}
              </div>
            )}
          </div>
        )}

        <div className="rounded-xl border border-ink/15 bg-page px-6 pb-6 pt-5 shadow-[0_1px_0_var(--color-line)]">
          <label htmlFor="child_name" className="font-display text-xl text-ink">
            This book is for
          </label>
          <input
            id="child_name"
            autoComplete="off"
            maxLength={20}
            required
            value={brief.child_name}
            onChange={(e) => set("child_name", e.target.value)}
            placeholder="Your child's first name"
            className="mt-1 w-full border-0 border-b-2 border-ink/15 bg-transparent pb-1 font-display text-3xl text-ink placeholder:text-ink-soft/50 focus:border-saffron-deep focus:outline-none"
            aria-invalid={!!fieldErrors.child_name}
            aria-describedby="child_name_error"
          />
          <FieldError id="child_name_error" text={fieldErrors.child_name} />

          <div className="mt-5">
            <span className="text-sm font-medium text-ink-soft" id="hero_label">
              The hero is a
            </span>
            <div
              className="mt-2 flex gap-2"
              role="radiogroup"
              aria-labelledby="hero_label"
            >
              {(["girl", "boy"] as const).map((h) => (
                <Pill
                  key={h}
                  selected={brief.hero === h}
                  onClick={() => set("hero", h)}
                >
                  {h === "girl" ? "Girl" : "Boy"}
                </Pill>
              ))}
            </div>
            <FieldError
              text={
                fieldErrors.hero ?? (missingHero ? "Choose girl or boy." : "")
              }
            />
          </div>

          <div className="mt-5">
            <span className="text-sm font-medium text-ink-soft" id="age_label">
              Age
            </span>
            <div
              className="mt-2 flex gap-2"
              role="radiogroup"
              aria-labelledby="age_label"
            >
              {AGES.map((a) => (
                <button
                  key={a}
                  type="button"
                  role="radio"
                  aria-checked={brief.age === a}
                  onClick={() => set("age", a)}
                  className={`h-10 w-10 rounded-full border text-base transition-colors ${
                    brief.age === a
                      ? "border-ink bg-ink text-page"
                      : "border-ink/15 bg-page text-ink hover:border-ink/40"
                  }`}
                >
                  {a}
                </button>
              ))}
            </div>
          </div>
        </div>

        <Field
          id="appearance"
          label="What do they look like?"
          hint="A few words is enough. Please don't describe or upload photos."
          error={fieldErrors.appearance}
        >
          <textarea
            id="appearance"
            rows={2}
            maxLength={150}
            required
            value={brief.appearance}
            onChange={(e) => set("appearance", e.target.value)}
            placeholder="Curly black hair, brown skin, round red glasses"
            className={inputClass}
          />
        </Field>

        <Field
          id="favourites"
          label="Favourite things"
          hint="These become the companion and the setting."
          error={fieldErrors.favourites}
        >
          <input
            id="favourites"
            maxLength={100}
            required
            value={brief.favourites}
            onChange={(e) => set("favourites", e.target.value)}
            placeholder="Elephants, mangoes"
            className={inputClass}
          />
        </Field>

        <Choice label="The story should be about">
          <div className="flex flex-wrap gap-2">
            {LESSONS.map((l) => (
              <Pill
                key={l.value}
                selected={brief.lesson === l.value}
                onClick={() => set("lesson", l.value)}
              >
                {l.label}
              </Pill>
            ))}
          </div>
          {brief.lesson === "custom" && (
            <div className="mt-3">
              <input
                aria-label="Your own lesson"
                maxLength={80}
                required
                value={brief.custom_lesson}
                onChange={(e) => set("custom_lesson", e.target.value)}
                placeholder="Saying thank you"
                className={inputClass}
              />
              <FieldError text={fieldErrors.custom_lesson} />
            </div>
          )}
        </Choice>

        <Choice label="Language">
          <div className="flex gap-2">
            {(
              [
                ["en", "English"],
                ["hi", "हिन्दी"],
              ] as [Language, string][]
            ).map(([value, label]) => (
              <Pill
                key={value}
                selected={brief.language === value}
                onClick={() => set("language", value)}
              >
                <span lang={value}>{label}</span>
              </Pill>
            ))}
          </div>
        </Choice>

        <Choice label="Pictures">
          <div className="grid grid-cols-3 gap-3">
            {STYLES.map((s) => (
              <button
                key={s.value}
                type="button"
                role="radio"
                aria-checked={brief.style === s.value}
                onClick={() => set("style", s.value)}
                className={`group overflow-hidden rounded-xl border-2 bg-page text-left transition-colors ${
                  brief.style === s.value
                    ? "border-saffron-deep"
                    : "border-transparent hover:border-ink/15"
                }`}
              >
                <img
                  src={`/img/style-${s.value}.jpg`}
                  alt=""
                  className="aspect-square w-full object-cover"
                />
                <span className="block px-2 py-1.5 text-sm">{s.label}</span>
              </button>
            ))}
          </div>
        </Choice>

        <Choice label="Length">
          <div className="flex gap-2">
            {([4, 8] as const).map((n) => (
              <Pill
                key={n}
                selected={brief.pages === n}
                onClick={() => set("pages", n)}
              >
                {n} pages
              </Pill>
            ))}
          </div>
        </Choice>

        <div className="flex flex-wrap items-center gap-x-5 gap-y-3">
          <Button type="submit">Write the story</Button>
          <p className="text-small text-ink-soft">
            You&rsquo;ll get a picture book (PDF) and a narrated read-along
            video.
          </p>
        </div>
      </fieldset>
    </form>
  );
}

const inputClass =
  "w-full rounded-xl border border-ink/15 bg-page px-3.5 py-2.5 text-base text-ink placeholder:text-ink-soft/60 focus:border-saffron-deep focus:outline-none";

function Field(props: {
  id: string;
  label: string;
  hint?: string;
  error?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label htmlFor={props.id} className="block font-medium">
        {props.label}
      </label>
      {props.hint && <p className="mb-2 text-sm text-ink-soft">{props.hint}</p>}
      {props.children}
      <FieldError text={props.error} />
    </div>
  );
}

function Choice({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div role="radiogroup" aria-label={label}>
      <p className="mb-2 font-medium">{label}</p>
      {children}
    </div>
  );
}

function Pill(props: {
  selected: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={props.selected}
      onClick={props.onClick}
      className={`rounded-lg border px-4 py-1.5 text-[0.95rem] transition-colors ${
        props.selected
          ? "border-ink bg-ink text-page"
          : "border-ink/15 bg-page text-ink hover:border-ink/40"
      }`}
    >
      {props.children}
    </button>
  );
}

function FieldError({ text, id }: { text?: string; id?: string }) {
  if (!text) return null;
  return (
    <p id={id} className="mt-1.5 text-sm text-danger">
      {text}
    </p>
  );
}
