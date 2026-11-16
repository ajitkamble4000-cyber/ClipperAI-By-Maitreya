import type { NextConfig } from "next";

/**
 * `STATIC_EXPORT=1` builds plain files for static hosting such as GitHub Pages (see lib/routes.ts and
 * DEPLOY.md). `PAGES_BASE_PATH` is the sub-path the site is served from, e.g. "/ClipperAI-By-Maitreya".
 * Without it, this is the normal Node server build (Vercel, Docker).
 */
const isStatic = process.env.STATIC_EXPORT === "1";
const basePath = (process.env.PAGES_BASE_PATH ?? "").replace(/\/$/, "");

const nextConfig: NextConfig = isStatic
  ? {
      output: "export",
      basePath: basePath || undefined,
      trailingSlash: true,
      images: { unoptimized: true },
      env: { NEXT_PUBLIC_STATIC: "1", NEXT_PUBLIC_BASE_PATH: basePath },
    }
  : {};

export default nextConfig;
