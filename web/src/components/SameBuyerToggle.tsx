"use client";

import { usePathname, useRouter } from "next/navigation";
import { useId } from "react";

/** URL-synced switch: `?same_buyer=1`. Other query parameters are kept. */
export function SameBuyerToggle({ checked }: { checked: boolean }) {
  const router = useRouter();
  const pathname = usePathname();
  const id = useId();
  return (
    <label htmlFor={id} className="inline-flex cursor-pointer items-center gap-2 text-sm text-ink">
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
        className="h-4 w-4 accent-[var(--accent)]"
      />
      Solo la misma entidad
    </label>
  );
}
