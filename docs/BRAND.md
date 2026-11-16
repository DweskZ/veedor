# Veedor brand

## Name
In Ecuador a *veedor* is a citizen overseer: someone who watches a public process and reports what the records show. The name positions the tool as an instrument for that role, not as an accuser.

**Tagline:** "Indicadores de riesgo, con su evidencia."

## Voice
- Sober, technical, plain Spanish. Describe what the data shows, with the value and the threshold.
- Use: "señal de riesgo", "indicador", "atípico", "no disponible", "revisión humana".
- Never use: "corrupto", "fraude", "irregular", "culpable", or anything that asserts wrongdoing. No alarm language, no exclamation marks, no imperatives to "denounce".
- Missing data is `null` and reads "No disponible". Never fill gaps.
- Natural persons appear as "Persona natural" with a masked RUC.
- Every page that shows indicators carries the disclaimer: "Veedor muestra indicadores de riesgo calculados sobre datos públicos. No constituyen acusaciones ni determinan responsabilidades."

## Identity
Metaphor: an open aperture (the overseer's field of view) around three tally bars of rising height (a measure, not a verdict). Aesthetic: audit report / open-data observatory on warm paper and ink. No red alarm colours, no handcuffs, money bags or magnifying glasses.

**Mark:** `web/src/components/Logo.tsx` (SVG, drawn in code): a ring with an open gap, three rounded bars in the accent colour. The ring uses `currentColor`. **Wordmark:** "Veedor" in Schibsted Grotesk 600, tight tracking. **Favicon:** `web/src/app/icon.svg` (dark tile). **Open Graph:** `web/src/app/opengraph-image.tsx`, generated in code (1200x630). No raster assets.

## Colour
Defined as CSS variables in `web/src/app/globals.css`; light is "Papel", dark is "Tinta" (related to the author's Washi/Sumi tones, with a teal accent so Veedor does not read as terracotta/alarm).

| Token | Light | Dark |
|---|---|---|
| bg | `#f4f0e6` | `#161412` |
| surface | `#fbf9f4` | `#1e1b18` |
| surface-2 | `#ece6d8` | `#28241f` |
| ink | `#1b1a17` | `#ece5d6` |
| muted | `#58544b` | `#ada594` |
| line | `#d6cfbd` | `#3c372f` |
| accent | `#1d5b6a` | `#7cc0cc` |
| accent-ink | `#f6f3ea` | `#0f1a1d` |

### Risk scale (presentation bands, not statistical thresholds)
Sequential, ordered by lightness so it survives colour-vision deficiency; every level also shows its number and label, so colour is never the only channel. Light theme darkens with risk, dark theme brightens with risk.

| Level | Score | Light bg / fg | Dark bg / fg |
|---|---|---|---|
| 0 Sin señales | 0 | `#e8e4d8` / `#3d392f` | `#2c2822` / `#cfc7b6` |
| 1 Bajo | 1-24 | `#ecd98f` / `#3f3205` | `#4a4326` / `#eadfb0` |
| 2 Moderado | 25-49 | `#dca43c` / `#33230a` | `#a8862a` / `#140e02` |
| 3 Elevado | 50-74 | `#a8531f` / `#fff8ee` | `#d98a4a` / `#1f1204` |
| 4 Alto | 75-100 | `#5e2347` / `#fbf1f6` | `#f0b8d2` / `#2b0f1f` |

### Verified contrast (WCAG 2.x ratio, computed with a script)
- Light: ink on bg 15.3, muted on bg 6.6, muted on surface 7.2, accent on bg 6.7, accent-ink on accent 6.9.
- Dark: ink on bg 14.7, muted on bg 7.5, accent on bg 9.0, accent-ink on accent 8.7.
- Risk label text on its fill: light 9.1 / 8.9 / 6.8 / 5.1 / 10.5; dark 8.7 / 7.4 / 5.6 / 6.7 / 10.5 (levels 0 to 4). All at least 4.5.
- Relative luminance of the fills is strictly monotonic per theme (light 0.776 to 0.040; dark 0.022 to 0.575). Low-level fills are close to the surface, so swatches carry a 1px border and a text label.

## Typography
- UI: **Schibsted Grotesk** (variable, via `next/font/google`), a serious grotesk with good Spanish diacritics.
- Codes, RUCs, OCIDs, amounts: **IBM Plex Mono** 400/500.
- Do not enable tabular-figure features on body text: they widen punctuation in this typeface. Numbers that must align use the mono face.

## Spacing, radius, motion
Tailwind 4px spacing scale; layout container 72rem with 16px (mobile) / 24px gutters; section rhythm 48px. Radius: 4px (chips, scores), 8px (inputs, buttons), 12px (cards). Focus: 2px accent outline, 2px offset. Motion: only a soft skeleton pulse, disabled under `prefers-reduced-motion`.
