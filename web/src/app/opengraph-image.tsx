import { ImageResponse } from "next/og";

export const alt = "Veedor, radar abierto de riesgo en contratación pública del Ecuador";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function OpengraphImage() {
  const ink = "#ece5d6";
  const accent = "#7cc0cc";
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          background: "#161412",
          color: ink,
          padding: 72,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 28 }}>
          <svg width="120" height="120" viewBox="0 0 32 32" fill="none">
            <circle cx="16" cy="16" r="13" stroke={ink} strokeWidth="2.5" strokeLinecap="round" strokeDasharray="64 17.7" transform="rotate(-30 16 16)" />
            <rect x="9.5" y="16" width="3.2" height="6" rx="1" fill={accent} />
            <rect x="14.4" y="12" width="3.2" height="10" rx="1" fill={accent} />
            <rect x="19.3" y="8" width="3.2" height="14" rx="1" fill={accent} />
          </svg>
          <div style={{ fontSize: 96, fontWeight: 700, letterSpacing: -2 }}>Veedor</div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          <div style={{ fontSize: 56, lineHeight: 1.15, maxWidth: 940 }}>Radar abierto de riesgo en contratación pública</div>
          <div style={{ fontSize: 30, color: "#ada594" }}>Indicadores con su evidencia. Sin acusaciones. Datos abiertos del SERCOP.</div>
        </div>
        <div style={{ display: "flex", gap: 14 }}>
          {["#4a4326", "#a8862a", "#d98a4a", "#f0b8d2"].map((c) => (
            <div key={c} style={{ width: 120, height: 10, borderRadius: 5, background: c }} />
          ))}
        </div>
      </div>
    ),
    size,
  );
}
