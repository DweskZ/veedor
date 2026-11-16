import type { ReactNode } from "react";
import { findTerm, termId } from "@/lib/glossary";
import { TermPopover } from "./TermPopover";

/**
 * Marks a procurement term with an inline definition. Use it on the first occurrence in a section.
 * `t` is the glossary term or an alias; when it is unknown the children render unmarked.
 */
export function Term({ t, children }: { t: string; children?: ReactNode }) {
  const e = findTerm(t);
  if (!e) return <>{children ?? t}</>;
  return (
    <TermPopover definition={e.definition_es} anchor={termId(e.term)}>
      {children ?? t}
    </TermPopover>
  );
}
