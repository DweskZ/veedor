import type { ReactNode } from "react";
import { Footer } from "./Footer";

/**
 * Main landmark and footer of a page. There is deliberately no Suspense boundary and no streaming around the content:
 * React sends a boundary's parts as they finish and relies on JavaScript to move them into place, so without JavaScript the
 * footer and the bodies of sections arrive out of order. A page without boundaries is sent complete, in document order.
 */
export function PageShell({ children }: { children: ReactNode }) {
  return (
    <>
      <main id="contenido" className="flex-1">
        {children}
      </main>
      <Footer />
    </>
  );
}

/** Kept for symmetry with pages that have no route parameters. */
export function PageFrame({ children }: { children: ReactNode }) {
  return <PageShell>{children}</PageShell>;
}
