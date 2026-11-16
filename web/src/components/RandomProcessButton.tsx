"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { randomProcess } from "@/lib/client-api";

/** Opens a random process that has at least one signal. Needs JavaScript, so it stays hidden without it. */
export function RandomProcessButton({ className = "btn btn--line btn--sm", label = "Proceso al azar" }: { className?: string; label?: string }) {
  const router = useRouter();
  const [state, setState] = useState<"idle" | "busy" | "error" | "none">("idle");
  return (
    <span className="needs-js rnd">
      <button
        type="button"
        className={className}
        aria-busy={state === "busy"}
        disabled={state === "busy"}
        onClick={async () => {
          setState("busy");
          try {
            const ocid = await randomProcess(true);
            if (!ocid) return setState("none");
            router.push(`/procesos/${encodeURIComponent(ocid)}`);
          } catch {
            setState("error");
          }
        }}
      >
        {state === "busy" ? "Buscando…" : label}
      </button>
      <span role="status" className={state === "error" || state === "none" ? "rnd__msg" : "sr-only"}>
        {state === "error" ? "No pudimos elegir un proceso ahora. Inténtalo de nuevo." : state === "none" ? "No hay procesos con señales para elegir." : ""}
      </span>
    </span>
  );
}
