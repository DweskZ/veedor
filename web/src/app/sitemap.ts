import type { MetadataRoute } from "next";
import { ALLOW_INDEXING, SITE_URL, STATIC_ROUTES } from "@/lib/site";

/** Empty until indexing is allowed. Lists static routes only, never a process, supplier or entity page. */
export default function sitemap(): MetadataRoute.Sitemap {
  if (!ALLOW_INDEXING) return [];
  return STATIC_ROUTES.map((path) => ({ url: `${SITE_URL}${path === "/" ? "" : path}` }));
}
