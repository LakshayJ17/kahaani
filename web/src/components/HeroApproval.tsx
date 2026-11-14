import { url, type Job } from "@/lib/api";

interface Props {
  job: Job;
  onApprove: () => void;
  onRetry: () => void;
}

export default function HeroApproval({ job, onApprove, onRetry }: Props) {
  return (
    <div>
      <p className="text-ink-soft">{job.forLine}</p>
      <h3 className="mt-1 text-3xl text-indigo" lang={job.language}>
        {job.title}
      </h3>
      <figure className="mt-5">
        <img
          src={url(job.heroUrl!)}
          alt="The hero of the story, drawn from your description"
          className="aspect-square w-full max-w-md rounded-sm bg-line object-cover shadow-[0_18px_40px_-24px_rgba(23,24,28,0.45)]"
        />
        <figcaption className="mt-3 max-w-md text-ink-soft">
          {job.reused === "story+pictures"
            ? "Another family asked for a story very like this one, so we've reused that checked book with your child's name. It's ready almost at once."
            : job.reused === "story"
              ? "This story was first written, and checked, for another child with a similar idea. Your child's pictures are new."
              : "Every page is drawn from this picture, so the hero looks the same throughout."}{" "}
          Does this look like your child?
        </figcaption>
      </figure>
      <div className="mt-5 flex flex-wrap gap-3">
        <button
          onClick={onApprove}
          className="rounded-full bg-indigo px-6 py-2.5 font-medium text-white hover:bg-indigo-deep"
        >
          Yes, draw the pages
        </button>
        <button
          onClick={onRetry}
          className="rounded-full border border-indigo/30 px-6 py-2.5 font-medium text-indigo hover:border-indigo"
        >
          Try a different picture
        </button>
      </div>
    </div>
  );
}
