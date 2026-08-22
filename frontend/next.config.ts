import type { NextConfig } from "next";

/**
 * Self-hosted mode: the browser calls same-origin /api/* and Next proxies it
 * to the kernel service (TRUSS_KERNEL_URL, baked at build time).
 * Vercel/demo mode: NEXT_PUBLIC_TRUSS_API points the browser straight at a
 * kernel URL, and the rewrite below is never used.
 */
const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    const kernel = process.env.TRUSS_KERNEL_URL ?? "http://127.0.0.1:8000";
    return [{ source: "/api/:path*", destination: `${kernel}/api/:path*` }];
  },
};

export default nextConfig;
