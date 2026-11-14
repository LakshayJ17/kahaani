"use client";

import { Play } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Reveal } from "@/components/ui/Reveal";
import { api, url, type Sample } from "@/lib/api";

const POINTS = [
  "Every page is read aloud in a warm Hindi or Indian English voice.",
  "Each page stays on screen for as long as it is read, so little ones can follow the words.",
  "Watch it on a phone or TV, or download the video for car rides and grandparents.",
];

/** Shows off the narrated video that comes with every book, using a real sample. */
export function ReadAlong() {
  const [sample, setSample] = useState<Sample | null>(null);
  const [playing, setPlaying] = useState(false);
  const video = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    api
      .samples()
      .then((all) =>
        setSample(
          all.find((s) => s.videoUrl && s.id === "b02") ??
            all.find((s) => s.videoUrl) ??
            null,
        ),
      )
      .catch(() => setSample(null));
  }, []);

  return (
    <section
      id="read-along"
      aria-labelledby="read-along-title"
      className="page-x mx-auto max-w-7xl scroll-mt-6 py-16 lg:py-24"
    >
      <Reveal className="grid items-center gap-10 lg:grid-cols-[1fr_1.35fr] lg:gap-16">
        <div>
          <h2 id="read-along-title" className="text-head">
            Every book is also a read-along video
          </h2>
          <ul className="mt-6 space-y-3">
            {POINTS.map((p) => (
              <li key={p} className="flex gap-3 text-ink-soft">
                <span
                  className="mt-2.5 size-2 shrink-0 rounded-full bg-saffron"
                  aria-hidden="true"
                />
                {p}
              </li>
            ))}
          </ul>
        </div>

        {/* A little screen on the desk, playing a real sample. */}
        <div className="rounded-[18px] bg-ink p-3 shadow-[0_40px_60px_-30px_rgb(43_33_24/0.7)] sm:p-4">
          <div className="relative overflow-hidden rounded-[10px] bg-black">
            {sample?.videoUrl ? (
              <>
                <video
                  ref={video}
                  src={url(sample.videoUrl)}
                  poster={url(sample.coverUrl)}
                  controls={playing}
                  playsInline
                  preload="metadata"
                  onPlay={() => setPlaying(true)}
                  className="aspect-[16/10] w-full object-contain"
                />
                {!playing && (
                  <button
                    onClick={() => {
                      setPlaying(true);
                      video.current?.play();
                    }}
                    className="group absolute inset-0 flex flex-col items-center justify-center gap-3 bg-ink/35 text-page"
                    aria-label={`Play the read-along of ${sample.title}`}
                  >
                    <span className="flex size-20 items-center justify-center rounded-full bg-saffron text-ink shadow-[0_4px_0_var(--saffron-deep)] transition-transform duration-200 group-hover:scale-105">
                      <Play
                        className="ml-1 size-9 fill-current"
                        strokeWidth={1.5}
                      />
                    </span>
                    <span className="font-display text-lead">
                      Play &ldquo;{sample.title}&rdquo;
                    </span>
                  </button>
                )}
              </>
            ) : (
              <div className="aspect-[16/10] w-full" aria-busy="true" />
            )}
          </div>
          <div
            className="mx-auto mt-3 h-1.5 w-16 rounded-full bg-page/20"
            aria-hidden="true"
          />
        </div>
      </Reveal>
    </section>
  );
}
