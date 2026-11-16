import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { ImageResponse } from "next/og";

export const alt = "veedor. Mira cómo compra el Estado. Un producto de ruray.";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

const bold = await readFile(join(process.cwd(), "assets/jakarta-800.ttf"));
const medium = await readFile(join(process.cwd(), "assets/jakarta-500.ttf"));

/** Same composition as the Ruray site's og image: ice background, huge wordmark, terracotta circle. */
export default function OpengraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          position: "relative",
          background: "#E3EEFF",
          color: "#1A1F36",
          fontFamily: "Jakarta",
        }}
      >
        <div style={{ position: "absolute", width: 640, height: 640, borderRadius: 320, background: "#D9480F", right: -190, top: 20, display: "flex" }} />
        <div style={{ position: "absolute", left: 72, top: 60, display: "flex", alignItems: "baseline", fontWeight: 800, fontSize: 40, letterSpacing: -1.6 }}>
          <span>un producto de</span>
          <span style={{ marginLeft: 12, display: "flex", alignItems: "baseline" }}>
            ruray<span style={{ width: 8, height: 8, borderRadius: 4, background: "#D9480F", marginLeft: 3, display: "flex" }} />
          </span>
        </div>
        <div style={{ position: "absolute", left: 72, top: 170, display: "flex", alignItems: "baseline", fontWeight: 800, fontSize: 156, lineHeight: 1, letterSpacing: -7.8 }}>
          veedor
          <div style={{ width: 26, height: 26, borderRadius: 13, background: "#D9480F", marginLeft: 8, display: "flex" }} />
        </div>
        <div style={{ position: "absolute", left: 76, bottom: 56, display: "flex", fontWeight: 500, fontSize: 40, letterSpacing: -1, width: 560, lineHeight: 1.15 }}>
          Mira cómo compra el Estado.
        </div>
      </div>
    ),
    {
      ...size,
      fonts: [
        { name: "Jakarta", data: bold, weight: 800, style: "normal" },
        { name: "Jakarta", data: medium, weight: 500, style: "normal" },
      ],
    },
  );
}
