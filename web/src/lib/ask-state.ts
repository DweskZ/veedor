import { useSyncExternalStore } from "react";

/**
 * In-memory switch: set when the API answers 404 to a question (the route was turned off after the page was built).
 * The section and its entry in the section bar then disappear. Never persisted.
 */
let off = false;
const listeners = new Set<() => void>();

export function markAskOff(): void {
  if (off) return;
  off = true;
  listeners.forEach((l) => l());
}

const subscribe = (l: () => void) => {
  listeners.add(l);
  return () => listeners.delete(l);
};

export const useAskOff = (): boolean =>
  useSyncExternalStore(
    subscribe,
    () => off,
    () => false,
  );
