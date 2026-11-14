"use client";

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useEffect, useRef, useState, type ReactNode } from "react";

interface Props {
  left: ReactNode;
  right: ReactNode;
  /** Change this to turn the page; `direction` 1 turns forward (right to left), -1 back. */
  turnKey?: string | number;
  direction?: 1 | -1;
  leftNumber?: ReactNode;
  rightNumber?: ReactNode;
  /** Things that hang from the spine, e.g. ribbon bookmarks. */
  spine?: ReactNode;
  className?: string;
  rightClassName?: string;
}

const TURN_SECONDS = 0.8;

/**
 * An open hardback: maroon cover, two pages curving into the spine, stacked page edges,
 * and a paper leaf that turns over the spine whenever `turnKey` changes.
 */
export function OpenBook({
  left,
  right,
  turnKey,
  direction = 1,
  leftNumber,
  rightNumber,
  spine,
  className = "",
  rightClassName = "",
}: Props) {
  const reduce = useReducedMotion();
  const [leaves, setLeaves] = useState<{ id: number; dir: 1 | -1 }[]>([]);
  const first = useRef(true);
  const counter = useRef(0);

  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    if (reduce) return;
    const id = ++counter.current;
    setLeaves((l) => [...l, { id, dir: direction }]);
    const t = setTimeout(
      () => setLeaves((l) => l.filter((x) => x.id !== id)),
      TURN_SECONDS * 1000 + 50,
    );
    return () => clearTimeout(t);
    // Only a new turnKey starts a turn.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [turnKey]);

  return (
    <div className={`relative ${className}`}>
      <div className="book-cover rounded-[14px] p-2.5 sm:p-3.5">
        <div className="relative grid [perspective:4200px] md:grid-cols-2">
          <div className="book-page book-page-left overflow-hidden md:min-h-[480px]">
            <AnimatePresence initial={false} mode="popLayout">
              <motion.div
                key={`l-${turnKey}`}
                className="h-full"
                initial={{ opacity: 0 }}
                animate={{
                  opacity: 1,
                  transition: { delay: reduce ? 0 : TURN_SECONDS * 0.55 },
                }}
                exit={{
                  opacity: 0,
                  transition: { delay: reduce ? 0 : TURN_SECONDS * 0.5 },
                }}
              >
                {left}
              </motion.div>
            </AnimatePresence>
            {leftNumber != null && (
              <span className="pointer-events-none absolute bottom-2.5 left-0 right-0 text-center font-display text-small text-ink-soft">
                {leftNumber}
              </span>
            )}
          </div>

          <div
            className={`book-page book-page-right overflow-hidden ${rightClassName}`}
          >
            <AnimatePresence initial={false} mode="popLayout">
              <motion.div
                key={`r-${turnKey}`}
                className="h-full"
                initial={{ opacity: 0 }}
                animate={{
                  opacity: 1,
                  transition: { delay: reduce ? 0 : 0.15 },
                }}
                exit={{ opacity: 0 }}
              >
                {right}
              </motion.div>
            </AnimatePresence>
            {rightNumber != null && (
              <span className="pointer-events-none absolute bottom-2.5 left-0 right-0 text-center font-display text-small text-ink-soft">
                {rightNumber}
              </span>
            )}
          </div>

          {/* The fold where the pages meet the binding. */}
          <div
            aria-hidden="true"
            className="book-gutter pointer-events-none absolute inset-y-0 left-1/2 hidden w-14 -translate-x-1/2 md:block"
          />

          {/* Turning leaves: forward turns lift from the right page and land on the left. */}
          {leaves.map(({ id, dir }) => (
            <motion.div
              key={id}
              aria-hidden="true"
              className="pointer-events-none absolute inset-y-0 z-30 hidden w-1/2 md:block"
              style={{
                [dir === 1 ? "right" : "left"]: 0,
                transformOrigin: dir === 1 ? "left center" : "right center",
                transformStyle: "preserve-3d",
              }}
              initial={{ rotateY: 0 }}
              animate={{ rotateY: dir === 1 ? -180 : 180 }}
              transition={{
                duration: TURN_SECONDS,
                ease: [0.45, 0.05, 0.25, 1],
              }}
            >
              <div
                className={`book-leaf absolute inset-0 ${dir === 1 ? "book-leaf-front" : "book-leaf-back"}`}
              />
              <div
                className={`book-leaf absolute inset-0 ${dir === 1 ? "book-leaf-back" : "book-leaf-front"}`}
                style={{ transform: "rotateY(180deg)" }}
              />
            </motion.div>
          ))}
        </div>
      </div>
      {spine}
    </div>
  );
}
