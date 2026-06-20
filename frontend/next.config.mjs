import { dirname } from "path";
import { fileURLToPath } from "url";

/** @type {import('next').NextConfig} */

// Proxy /api/* to the FastAPI backend so the signed session cookie stays
// same-origin (no CORS, no cross-site cookie headaches). Override the target
// with BACKEND_URL in deployment.
const backend = process.env.BACKEND_URL || "http://localhost:8000";

const nextConfig = {
  // Pin the workspace root to this folder (a stray lockfile elsewhere can
  // otherwise confuse Next's root inference).
  outputFileTracingRoot: dirname(fileURLToPath(import.meta.url)),
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backend}/:path*` }];
  },
};

export default nextConfig;
