import type { PartyKind } from "./types";

/** Route-parameter validation. Anything else is a 404 without calling the API. */
export const isRuc = (v: string) => /^\d{13}$/.test(v);
export const isOcid = (v: string) => /^(?:ocds-[a-z0-9]+|sample-ocid)-[A-Za-z0-9._-]{1,100}$/.test(v);

/** A supplier page exists only for identified companies and public entities, never for masked or unknown parties. */
export const canLinkSupplier = (ruc: string | null, kind: PartyKind | null) =>
  !!ruc && isRuc(ruc) && (kind === "company" || kind === "public_entity");

export const canLinkBuyer = (ruc: string | null) => !!ruc && isRuc(ruc);
