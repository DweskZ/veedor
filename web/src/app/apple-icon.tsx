import { ImageResponse } from "next/og";

export const size = { width: 180, height: 180 };
export const contentType = "image/png";

/** Same mark as icon.svg: ink tile, ice "v", terracotta dot. Generated in code. */
export default function AppleIcon() {
  return new ImageResponse(
    (
      <div style={{ width: "100%", height: "100%", display: "flex", background: "#1A1F36" }}>
        <svg width="180" height="180" viewBox="0 0 64 64">
          <path d="M14 22 L26 44 L38 22" fill="none" stroke="#E3EEFF" strokeWidth="7" strokeLinecap="round" strokeLinejoin="round" />
          <circle cx="48" cy="42" r="8" fill="#D9480F" />
        </svg>
      </div>
    ),
    size,
  );
}
