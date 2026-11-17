import { API } from "./env";

/** Waits (up to 90 s) for the site and the API, so a restarting dev stack does not show up as a test failure. */
export default async function globalSetup() {
  const base = process.env.E2E_BASE_URL ?? "http://localhost:3100";
  const targets = [`${base}/`, `${API}/processes/random?with_signals=true`];
  const deadline = Date.now() + 90_000;
  for (const url of targets) {
    for (;;) {
      try {
        if ((await fetch(url)).ok) break;
      } catch {
        /* not up yet */
      }
      if (Date.now() > deadline) throw new Error(`Not reachable: ${url}`);
      await new Promise((r) => setTimeout(r, 1500));
    }
  }
}
