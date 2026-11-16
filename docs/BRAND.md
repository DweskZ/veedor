# Veedor — a Ruray product

Veedor is built by Ruray (founder: Luis Figueroa) and wears the Ruray identity. This file says how Veedor inherits the Ruray system, what it adds, what it deliberately does not use, and where it still departs from it. The Ruray brand guide (`ruray-brand/BRAND.md`) is the parent; where this file is silent, that one decides.

The one rule that outranks every other design decision: **it must be clear.** A visitor who knows nothing about public procurement has to understand within seconds what this is, what it shows and what it does not.

## Name and line

- *Veedor*: in Ecuador, a citizen overseer who watches a public process. The tool is an instrument for that role, never an accuser.
- Headline idea: **"Mira cómo compra el Estado."** (look at how the State buys). It says what the product is in plain words, and it does not judge anyone.
- Ruray slogan, kept as is: **"Hazlo real."** Location line: **"Ecuador · Australia"**. Instagram: `@ruray.tech` (https://www.instagram.com/ruray.tech/).

## Credit (required by the owner)

- Header: a compact "un producto de ruray." under the Veedor wordmark (the word *ruray.* links to the Instagram profile).
- Footer on every page: **"Hecho por ruray."** (the Ruray wordmark, linking to the Instagram profile), **"Luis Figueroa, fundador de Ruray."**, and **"Hazlo real. · Ecuador · Australia"**.
- No employer or client is named anywhere.

## What Veedor inherits from Ruray

### Palette: "ice and terracotta"

One theme. There is no dark mode and no theme toggle: ink is a *section* background, not a global mode.

| Token | Hex | Role |
|---|---|---|
| Ice | `#E3EEFF` | Main background |
| Ink | `#1A1F36` | Text, outlines, dark sections |
| Terracotta | `#D9480F` | The one accent: key words, buttons, the circle, accent sections |
| White | `#FFFFFF` | Card fills, text on terracotta |
| Ice deep | `#CADBFB` | Dividers, tracks, secondary fills |
| Muted | `#5B6384` | Secondary text |

Backgrounds are ice, ink or terracotta only. Sections alternate ice / ink / terracotta so the page does not look washed out. Tokens live in `web/src/app/globals.css` (`:root`).

### Typography

Plus Jakarta Sans for everything, self-hosted (`web/public/fonts/`, four woff2 files for weights 500, 600, 700 and 800, loaded with `next/font/local`; no request to Google). Codes, RUCs and amounts use the same family with `font-variant-numeric: tabular-nums`; the previous monospace face is gone.

| Use | Weight | Tracking | Line height |
|---|---|---|---|
| Display / headlines | 800 | `-0.04em` to `-0.05em` | 0.92–1 |
| Lead / supporting line | 500 | `-0.02em` | 1.25–1.4 |
| Eyebrow labels | 800, uppercase | `0.14em`, with a terracotta dot | — |
| Buttons | 700–800 | `-0.02em` | 1.1 |

Headlines are large and broken by hand into short lines with the key word in terracotta (ink on terracotta).

### Wordmark family

Lowercase, weight 800, followed by a small terracotta dot: `veedor.` The construction is the same CSS as Ruray's `.wm` (`web/src/app/globals.css`, class `.wm`, dot `0.17em`). The Ruray wordmark appears only as a credit and is reproduced, not redesigned; the Ruray logo is still provisional.

### Shapes and the circle

- Pill buttons, 56 px tall, 3 px border (44 px for compact ones).
- White cards with 3 px ink borders and large radius (as the phone mockups of the Ruray site).
- The large terracotta circle bleeding off the edge is the signature motif: behind the hero illustration on the home page and top right of every inner page header (wide screens only, so it never sits behind text).
- Numbered terracotta pins (white numerals, large bold) link the three steps of "Cómo leerlo" to what they describe, as in the Ruray *maqueta* pieces. Connector lines are never drawn across an illustration.

### Motion

Only meaningful reveals, as on the Ruray site: sections rise into view once, and the hero illustration rises on load. Nothing bobs, floats or loops. Under `prefers-reduced-motion` all of it is off (the reveal script adds the visible state immediately; the skeleton does not pulse).

## The risk scale

Five presentation bands for the 0–100 score. They are display bins, not statistical thresholds. The scale runs from ice-deep to ink and **terracotta is reserved for the top band**. It is distinguishable without colour in three ways at once: the level name in words, the number of filled bars in a four-bar ascending glyph (a shape and position cue), and the colour.

| Level | Score | Chip fill / text | Bars | Label |
|---|---|---|---|---|
| 0 | 0 | `#FFFFFF` / `#1A1F36`, 2 px ink border | 0 of 4 | Sin señales |
| 1 | 1–24 | `#CADBFB` / `#1A1F36` | 1 of 4 | Bajo |
| 2 | 25–49 | `#8FA6DB` / `#1A1F36` | 2 of 4 | Moderado |
| 3 | 50–74 | `#1A1F36` / `#E3EEFF` | 3 of 4 | Elevado |
| 4 | 75–100 | `#D9480F` / `#FFFFFF` (large bold only) | 4 of 4 | Alto |

The number inside the chip is always 20 px / weight 800 or larger, which is "large text" for WCAG; the level name is always printed next to the chip in ink on white or ice.

### Contrast, measured (WCAG 2.x relative luminance)

Computed with a script over the exact hex values above.

| Foreground on background | Ratio | Used for | Needs |
|---|---|---|---|
| ink on ice | 13.87 | body text | 4.5 |
| ink on white | 16.24 | text in cards and tables | 4.5 |
| muted on ice | 5.04 | secondary text on the page | 4.5 |
| muted on white | 5.89 | labels and hints in cards | 4.5 |
| ice on ink | 13.87 | dark sections, table heads, footer, risk 3 | 4.5 |
| ice-deep on ink | 11.63 | secondary text on ink | 4.5 |
| ink on ice-deep | 11.63 | risk 1, legend | 4.5 |
| ink on `#8FA6DB` | 6.69 | risk 2 | 4.5 |
| white on terracotta | 4.30 | large bold text only: buttons (19 px / 700), pins, risk 4 number, the evaluation sentence | 3.0 (large) |
| terracotta on ice | 3.67 | headline key words only (40 px+) | 3.0 (large) |
| terracotta on ink | 3.78 | headline key words on ink sections only (40 px+) | 3.0 (large) |
| terracotta focus ring on ice | 3.67 | non-text, 3 px outline | 3.0 |
| ice focus ring on ink | 13.87 | non-text, in ink sections and footer | 3.0 |
| ink focus ring on terracotta | 3.78 | non-text, in the terracotta section | 3.0 |

Pairs that fail and are therefore **never used**: muted on ice-deep (4.22) and white on terracotta at small sizes (4.30 < 4.5). Consequences: nothing small is ever set on terracotta, the eyebrow on the terracotta section is an ink pill, and small text never sits on ice-deep.

The two lightest chips (white and ice-deep) are close to the page background (1.17 and 1.19), so every chip carries a 2 px ink border.

## Illustrations: isometric models made with Codex

Method (from the Ruray guide, section 8): `codex exec --skip-git-repo-check -s workspace-write -C <dir> -i oficina.png -i proceso.png - < prompt.txt`, the prompt through stdin, two existing Ruray *maquetas* as style references, an exact filename, no other files. The five prompts shared this text and differed only in the subject:

> Match the style of the two reference images exactly (same line weight, same isometric angle, same scale on the base, same amount of detail, same palette). Style: isometric scale model on a thin rounded square base, flat hand-drawn ink line art, ink outlines #1A1F36, white fills, pale ice-blue shading #CADBFB, terracotta #D9480F on a few small elements only. Technical illustration, not cute, not toy-like. No faces, no people, no text, no letters, no numbers, no signs with writing, no logos, no real brands or flags. The model occupies the lower two thirds of the canvas; the upper third stays empty. Square canvas 1254 x 1254 pixels, transparent background (if you cannot output transparency, use flat pure magenta #FF00FF as the background). Save only the single PNG file with the exact filename given, in the current directory. Do not write code files or any other files.

Subjects:

| File | Subject (the part of the prompt after "Subject:") | Used for |
|---|---|---|
| `hero` | a small public square: a modest town hall with columns, a construction site with a crane, a delivery truck on a road. "What the State buys: works, goods and services." Terracotta only on the truck and the crane | Home hero |
| `datos` | an archive building cut away to show rows of filing shelves with boxes and binders, a loading ramp and stacked boxes outside. "Open public data" | Step 1, "Elige un proceso" |
| `investigacion` | a desk office with a central round table and four distinct work stations (papers and magnifying glass; laptop and chart; filing cabinet; map and pinboard), no people | "Investiga con agentes" |
| `verificacion` | a public registry office with a service counter, glass partition, stamp, rope stanchions and filing drawers, no people, no writing | Step 3, "Verifica en la fuente oficial" |
| `vacio` | an empty fenced lot with a bare tree, a blank sign post and a few stones | Empty states and the 404 |

All five came back at 1254 × 1254 with a real alpha channel on the first attempt (no magenta keying was needed) and matched the references: ink outlines, white fills, pale blue shading, terracotta on one or two items, no text, no people, no faces. Production: cropped to the lower 1254 × 874 band (the upper empty third is removed, the same crop for all five so they stay one scale), converted to WebP at 960 and 480 px wide (`web/public/art/<name>-960.webp`, `-480.webp`), with explicit `width`/`height` and Spanish `alt` text (`web/src/components/Art.tsx`). Below the fold they are lazy-loaded. Sources and the prompt files live in `web/art-src/`, which is git-ignored.

No image contains or implies a real entity, person or brand. The one UI mockup on the home page (the sample "Oferente único" card) is drawn in HTML and CSS, as the Ruray guide asks for mockups, and carries the label "Ejemplo ilustrativo, no es un proceso real."

Rules to keep: ink outlines and white fills only, terracotta on a few elements, no people or faces, no text in the image (text is always HTML), upper third empty, one scale across the set. Always look at an image before using it and reject anything that reads as a toy or does not match the references.

## Voice

- Serious and trustworthy first, warm second. Plain words, no jargon, neutral Spanish with "tú", short sentences, one idea per block.
- Say "procesos analizados", never "marts"; "quién ganó", never "adjudicatario" in headings and labels (the contract word may remain in dense reference text).
- Nothing invented: no numbers, clients, results or urgency. Every figure comes from the API or from the generated evaluation snapshot (`web/src/data/eval-snapshot.json`); the evaluation sentence on the home page is built from that snapshot, not typed.
- Wording rules of `docs/CONTRACT.md` still hold: "señal de riesgo", "indicador", "atípico". Never "corrupto", "fraude", "irregular", "culpable" or anything that asserts wrongdoing. Indicators are not accusations; the home page, every signal card, the footer and the methodology say so. Natural persons are never named: "Persona natural" with the masked RUC.
- Each risk signal answers three questions in plain words: what was observed, why it can matter, how it can be perfectly normal (`web/src/lib/signal-copy.ts`, taken from the false-positive notes of `docs/METHODOLOGY.md`). Context signals are quieter (outlined, no points) and say so.
- Missing data reads "No disponible". Never fill gaps.

## Deliberately not used, and why

| Not used | Why |
|---|---|
| Dark mode, theme toggle | One theme, as Ruray. Ink is a section colour only. |
| Monospace for codes and labels | Rejected by the founder as the "dark tech" look. Tabular figures in Plus Jakarta Sans instead. |
| Gradients, glows, grid backgrounds, shadows with colour | Rejected outright by the founder. |
| Hues outside ice, ink and terracotta (red/amber/green traffic lights, a teal accent) | Not in the palette. A traffic-light scale would also read as a verdict, against the contract. The scale goes from ice-deep to ink and keeps terracotta for the top band. |
| Mascots, characters, robots, people in illustrations | Rejected by the founder (Ruray guide, "Rejected directions"). The four specialists are drawn as four work stations, not as figures. |
| Stock images, other image generators | The brand method is Codex with the Ruray maquetas as references. |
| Screenshots of Ruray apps or client work | Not Veedor's to show. |
| Chart libraries | Bars are plain HTML lists with the value as text. |
| Terracotta text at small sizes, muted text on ice-deep | Fail WCAG AA (see the table above). |
| The previous mark (ring and three bars) and the "Papel / Tinta" palette | Replaced by the wordmark family. |

## Components worth knowing

- `Art`, `Logo`, `ui.tsx` (page header, sections, figures, risk score and legend, bars, empty and error states, skeleton), `ProcessTable` (a table from 880 px, one card per process below), `SignalCard`, `AgentDiagram` (SVG in line style from 1100 px, numbered list below), `Nav` (pills from 880 px, a "Menú" button below).
- Focus: a 3 px terracotta outline (ice on ink sections, ink on the terracotta section).
- Targets: buttons, links and controls are at least 44 px; signal chips extend their hit area with a pseudo-element.
- Open Graph image, apple-touch icon and favicon are generated in code (`opengraph-image.tsx`, `apple-icon.tsx`, `icon.svg`) in the style of the Ruray site's image: ice background, huge `veedor.` and a terracotta circle. The OG route needs TTF fonts, so `web/assets/jakarta-*.ttf` are decompressed copies of the same woff2 files.

## Where Veedor still departs from the Ruray site

- Hero headline: three lines at about 8 rem instead of Ruray's two lines at 10.5 rem, because the line is longer.
- The hero illustration is an isometric model, where the Ruray site shows phone mockups.
- Veedor has dense data (tables, evidence lists, long official names in capitals) that the marketing site does not. Those areas follow the tokens but are necessarily busier than the Ruray site.
- Sections alternate ice / ink / terracotta on the home page only. Inner pages are ice with white cards (an ink band would hurt long reading and tables); the terracotta circle and the pills carry the brand there.
- The Ruray site pins numbers on a single model; here the three steps each have their own panel (two with a model, one with a sample card).
- English is not provided (Ruray's Australian audience does not use this product).

## Departures for a data product (stage 4)

The owner asked for the Ruray identity as the base and for improvements wherever a data product needs them, as long as the result is clearly the same family. Everything below keeps the palette, the typeface, the wordmark, the credit, the plain tone, and the rejected list (no gradients, glows, grid backgrounds, monospace, dark-tech look). Styles live in `web/src/app/data.css`.

| Departure | What changed | Why |
|---|---|---|
| Calmer page titles on inner pages | `.h1--page`: 2 to 3.5 rem, line height 1.04, balanced wrapping. The giant display style stays on the home page only. The terracotta circle is 300 px instead of 440 px. | A data page has to show its content in the first screen. At 8 rem the explorer and the map pushed the filters and the map below the fold. |
| Neutral surface tint | `--surface: #F1F6FF`, halfway between ice and white. Used for table row hover and quotation boxes, never for text. | Rows and quotations need a quiet fill that is neither the page nor a white card. Derived from the palette, not a new hue. |
| Tighter type scale for dense screens | `--fs-2xs` .75, `--fs-xs` .8125, `--fs-sm` .9375, `--fs-md` 1 rem for labels, table heads, helper text. Fact labels are sentence case, weight 700, no longer uppercase with wide tracking. | Uppercase tracked labels are right for an eyebrow and tiring for fourteen rows of labels. The eyebrow stays uppercase. |
| Spacing and radius tokens | `--s1..s5` (4 px steps), `--rad-ctl` 14, `--rad-card` 24. Cards and controls keep the 3 px ink border and large radius of the Ruray site. | One scale instead of many one-off numbers. |
| Names in readable case | Official names in capitals are shown in title case by a tested formatter (`web/src/lib/names.ts`, test `names.test.ts`). It keeps acronyms and legal forms (GAD, EP, IESS, S.A., CIA. LTDA.). The original spelling is the `title` attribute. Identifiers, RUCs and codes are never touched. | Long official names in capitals are the hardest text in the product to scan. The formatter is display only and cannot invent text; it is imperfect for unknown acronyms that look like words (they become "Digmat"), which is why the original stays one hover away. |
| Section navigation on long pages | `SectionNav`: a sticky bar of anchor links (Datos, Señales, Citas, Investigación, Parecidos, Expediente, Fuentes) that marks the group being read with `aria-current="location"`. It replaces the side index. | The process page is long. Anchors work without JavaScript, nothing is hidden, and the reader always knows where they are. Tabs were rejected: they would hide content from people without JavaScript and from printing. |
| Tables | Numbers right-aligned with tabular figures, 12 px row padding, the sorted column marked with a terracotta bar under its head and `aria-sort`, a header that sticks under the site header from 1100 px, rows that stack as cards on phones. | Scanning columns of amounts. Terracotta marks only "this is the active sort". |
| Filters | Search first (full width), then the selects. On phones the fields come first and the quick chips follow. A "Quitar los N filtros" button appears when any filter is active. The new chip "Más de USD 1 millón" uses `min_amount`. | The search box is the primary action of the explorer. |
| Source markers | A document icon-button next to each fact opens a side panel (bottom sheet on phones) with the source, original field, whether Veedor computed it, retrieval date, licence, how to verify, and "Copiar cita". Toggle "Mostrar fuentes" prints the source name next to every marker. | The founder's rule is "it must be clear" and the contract's rule is that every statement is traceable. The panel is a native modal dialog (Esc closes, focus returns). |
| Quotations from the source | Dashed outline box, a 4 px ink bar at the left of each passage, attribution line with author, date and original field. A note states that the words are not Veedor's. The dashed outline is the same cue already used for quiet context signals ("not part of the score"). | A quotation has to look different from Veedor's own text at a glance. |
| Icons | One family: 24 px grid, 2 px stroke, round caps, no fill (`Icon.tsx`: source, copy, check, up, close, quote, external). | Consistency with the line-art illustrations. |
| Back to top, copy buttons, "/" shortcut | A "Volver arriba" button after a long scroll; "Copiar" for the process code, the OCDS identifier and each citation (with a spoken and visible "Copiado"); "/" focuses the search. | Repeated use of a long page and of a data tool. All respect reduced motion and are hidden without JavaScript where they cannot work. |
| Map legend wording | Classes are cut on the one-decimal values that are shown, and written as "menos de A", "A a menos de B", "B o más". | Ranges built from observed minimum and maximum looked as if they touched ("31 % a 31,6 %" next to "31,6 % a 35,1 %"). |
| Home, three steps | Title "Cómo usar Veedor en tres pasos" under the eyebrow "Cómo funciona"; the number sits in the same corner of every card, repeated in text as "Paso 1 de 3"; each card links to where the step is done; the step illustrations load eagerly and the cards no longer wait for the reveal animation. | The previous title did not say steps for what, and a lazy image inside a hidden card could leave a card top empty in screenshots. |

Still not used, and why: tabs that hide content, a dark mode, a table library, a chart library, toast stacks, coloured status badges. Terracotta stays the one accent: primary buttons, the active-sort bar, the dot, the circle, the top risk band.

## Where Veedor still departs from the Ruray site (additions)

- Inner pages use a smaller title than the Ruray site's 10.5 rem two-line headline; only the home page keeps a large one.
- Dense reference screens (process page, tables) use the 4-step type scale above, which the marketing site does not have.
