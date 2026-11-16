"use client";

import { usePathname, useRouter } from "next/navigation";
import { useId } from "react";

/** URL-synced switch: `?same_buyer=1`. Other query parameters are kept. */
export function SameBuyerToggle({ checked }: { checked: boolean }) {
  const router = useRouter();
  const pathname = usePathname();
  const id = useId();
  return (
    <label htmlFor={id} className="check">
      <input
        id={id}
        type="checkbox"
        checked={checked}
        onChange={(e) => {
          const sp = new URLSearchParams(window.location.search);
          if (e.target.checked) sp.set("same_buyer", "1");
          else sp.delete("same_buyer");
          const qs = sp.toString();
          router.replace(`${pathname}${qs ? `?${qs}` : ""}#similares`, { scroll: false });
        }}
      />
      Solo de la misma entidad
    </label>
  );
}
