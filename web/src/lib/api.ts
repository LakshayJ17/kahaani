// Types and calls for the Python API (kahaani/api.py). Every call carries the sign-in token.

import { API_BASE } from "./api-base";
import { authHeaders } from "./auth";

export { API_BASE };

export type Language = "en" | "hi";
export type Style = "watercolour" | "cartoon" | "folk";
export type Mood = "happy" | "curious" | "worried" | "brave" | "calm" | "proud";
export type Reuse = "none" | "story" | "story+pictures";

export interface BriefInput {
  child_name: string;
  age: number;
  hero: "girl" | "boy" | "";
  appearance: string;
  favourites: string;
  lesson: string;
  custom_lesson: string;
  language: Language;
  style: Style;
  pages: 4 | 8;
  use_taste?: boolean;
}

export interface Taste {
  tokens: string[];
  summary: string[];
  style: Style | null;
  evidence: number;
  likedBooks: number;
}

export interface Child {
  id: string;
  name: string;
  age: number;
  last: Pick<
    BriefInput,
    "hero" | "appearance" | "favourites" | "language" | "style" | "pages"
  > | null;
  taste: Taste;
}

export interface Feedback {
  rating: -1 | 0 | 1;
  tags: string[];
}

// Must match kahaani/taste.py TAGS.
export const FEEDBACK_TAGS: [string, string][] = [
  ["funny", "Funny"],
  ["calm", "Calm, good for bedtime"],
  ["adventure", "More adventure please"],
  ["too_long", "Too long"],
  ["too_short", "Too short"],
  ["too_easy", "Too easy"],
  ["too_hard", "Too hard"],
  ["preachy", "The lesson felt preachy"],
  ["loved_pictures", "Loved the pictures"],
  ["pictures_off", "Pictures weren't quite right"],
];

export interface ApiError {
  message: string;
  reasons?: string[];
  fields?: Record<string, string>;
}

export interface QualityCheck {
  name: string;
  status: "passed" | "fixed" | "flagged" | "skipped";
  detail: string;
}

export interface BookPage {
  number: number;
  text: string;
  mood: Mood;
  imageUrl: string;
}

/** A book being made (in memory on the server until it's saved). */
export interface Job {
  id: string;
  busy: boolean;
  action: "start" | "hero" | "finish" | "redo" | null;
  progress: number;
  step: string;
  queuePosition: number;
  error: ApiError | null;
  stage: "new" | "hero" | "saved";
  bookId: string | null;
  title?: string;
  language?: Language;
  forLine?: string;
  heroUrl?: string;
  reused?: Reuse;
}

/** A book in the family's library. */
export interface SavedBook {
  id: string;
  title: string;
  language: Language;
  forLine: string;
  childName: string;
  heroUrl: string;
  pages: BookPage[];
  pdfUrl: string;
  videoUrl: string;
  quality: QualityCheck[];
  warnings: string[];
  progressPage: number;
  readCount: number;
  reused: Reuse;
  reported: boolean;
  createdAt: number;
  job: Job | null; // a page being changed right now
  feedback: Feedback | null;
}

export interface ShelfBook {
  id: string;
  title: string;
  language: Language;
  pageCount: number;
  progressPage: number;
  readCount: number;
  lastReadAt: number | null;
  createdAt: number;
  reused: Reuse;
  coverUrl: string;
}

export interface Library {
  children: {
    childName: string;
    childId: string;
    taste: Taste;
    books: ShelfBook[];
  }[];
}

export interface Sample {
  id: string;
  title: string;
  blurb: string;
  coverUrl: string;
  pdfUrl: string;
  videoUrl: string | null;
}

export class RequestError extends Error {
  constructor(
    public detail: ApiError,
    public status: number,
  ) {
    super(detail.message);
  }
}

export const url = (path: string) => `${API_BASE}${path}`;

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(url(path), {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(await authHeaders()),
        ...init?.headers,
      },
    });
  } catch {
    throw new RequestError(
      {
        message: "Can't reach the server. Check your connection and try again.",
      },
      0,
    );
  }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail: ApiError = body?.error ?? {
      message:
        typeof body?.detail === "string"
          ? body.detail
          : "Something went wrong. Please try again.",
    };
    throw new RequestError(detail, res.status);
  }
  return body as T;
}

const post = (body?: unknown): RequestInit => ({
  method: "POST",
  body: body === undefined ? undefined : JSON.stringify(body),
});

export const api = {
  create: (brief: BriefInput, fresh = false) =>
    call<Job | { existingBookId: string; title: string }>(
      "/api/books",
      post({ ...brief, fresh }),
    ),
  job: (id: string) => call<Job>(`/api/jobs/${id}`),
  newHero: (id: string) => call<Job>(`/api/jobs/${id}/hero`, post()),
  approve: (id: string) => call<Job>(`/api/jobs/${id}/approve`, post()),

  library: () => call<Library>("/api/library"),
  book: (id: string) => call<SavedBook>(`/api/library/${id}`),
  progress: (id: string, page: number, finished = false) =>
    call<{ ok: boolean }>(
      `/api/library/${id}/progress`,
      post({ page, finished }),
    ),
  report: (id: string) =>
    call<{ ok: boolean }>(`/api/library/${id}/report`, post()),
  deleteBook: (id: string) =>
    call<{ ok: boolean }>(`/api/library/${id}`, { method: "DELETE" }),
  redo: (id: string, page: number, request: string) =>
    call<Job>(`/api/library/${id}/pages/${page}/redo`, post({ request })),

  feedback: (id: string, fb: Feedback) =>
    call<{ ok: boolean; taste: Taste }>(
      `/api/library/${id}/feedback`,
      post(fb),
    ),
  children: () => call<Child[]>("/api/children"),
  forgetTaste: (childId: string) =>
    call<{ ok: boolean }>(`/api/children/${childId}/taste`, {
      method: "DELETE",
    }),

  consent: () => call<{ ok: boolean }>("/api/me/consent", post()),
  deleteAccount: () =>
    call<{ ok: boolean; booksDeleted: number }>("/api/me", {
      method: "DELETE",
    }),

  samples: () => call<Sample[]>("/api/samples"),
};
