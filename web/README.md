# Kahaani website

Next.js (App Router, TypeScript, Tailwind CSS v4), exported as static files and served by
the Python API (`kahaani/api.py`).

```bash
# terminal 1: the API on :8000
uv run python -m kahaani.api
# terminal 2: the site on :3000, talking to the API (see .env.development)
cd web && npm install && npm run dev
```

`npm run build` writes `out/`. When `web/out` exists, `python -m kahaani.api` serves the
whole site on one port.

- `src/app/page.tsx`: the page (intro, maker, samples, privacy)
- `src/components/Maker.tsx`: the flow (form, progress, hero approval, reader), polling the API
- `src/lib/api.ts`: API types and calls
- `src/app/globals.css`: colours, fonts and the one page-turn animation
