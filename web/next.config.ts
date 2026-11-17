import type { NextConfig } from "next";

// The Content-Security-Policy is set per request in src/proxy.ts (it carries a nonce).

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  // No Cache Components / streaming boundaries around page content: a page is sent once it is complete, in document order.
  // (Streamed blocks that arrive out of place are only moved into position by JavaScript, so without it the footer and the
  // bodies of sections would end up in the wrong place.)
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=(), usb=()" },
        ],
      },
    ];
  },
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
