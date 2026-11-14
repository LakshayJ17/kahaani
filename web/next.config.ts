import type { NextConfig } from "next";

// Static export: `npm run build` writes plain HTML/CSS/JS to out/, which the Python
// server (kahaani.api) serves alongside the API. One free container, no Node at runtime.
const nextConfig: NextConfig = {
  output: "export",
  // Emit books/index.html rather than books.html, so the Python static server (which
  // maps folders to index.html) serves /books and /books/view on a refresh too.
  trailingSlash: true,
  images: { unoptimized: true },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
