# Procedure-amount thresholds, 2015-2026

Context for the threshold analysis in [VALIDATION.md](VALIDATION.md). The thresholds are not a risk signal and change no score. Every figure comes from an official SERCOP publication (portal.compraspublicas.gob.ec), checked on 2026-11-16; the code table is `src/veedor/domain/thresholds.py`. No figure is estimated.

## How the thresholds are defined

Until mid-2025 each procedure boundary is a fixed coefficient times the Presupuesto Inicial del Estado (PIE) of the year; SERCOP prints the PIE and the dollar figures. The coefficients, used identically in every year 2015-2024 (the arithmetic PIE x coefficient reproduces every dollar figure the sources print, rounded to the cent):

| Boundary | Coefficient of PIE |
|---|---|
| Ínfima cuantía / subasta inversa electrónica (goods and services) | 0.0000002 |
| Menor cuantía / cotización (goods and services) | 0.000002 |
| Cotización / licitación (goods and services) | 0.000015 |
| Menor cuantía / cotización (works) | 0.000007 |
| Cotización / licitación (works) | 0.00003 |
| Lista corta / concurso público (consultancy) | 0.000015 |

Menor cuantía and cotización apply to non-normalised goods and services; normalised ones use catalogue or subasta inversa above the ínfima amount. The consultancy boundary between direct hiring and lista corta (0.000002) is not analysed because direct hiring is not identifiable in the lake as the lower side.

## Verified table (USD)

| Year | PIE | Ínfima / SIE (goods, services) | Menor / cotización (goods, services) | Cotización / licitación (goods, services) | Menor / cotización (works) | Cotización / licitación (works) | Lista corta / concurso (consultancy) | Source |
|---|---|---|---|---|---|---|---|---|
| 2015 | 36,317,117,010.35 | 7,263.42 | 72,634.23 | 544,756.76 | 254,219.82 | 1,089,513.51 | 544,756.76 | [source](https://portal.compraspublicas.gob.ec/sercop/?p=32320) |
| 2016 | 29,835,098,320.79 | 5,967.02 | 59,670.20 | 447,526.47 | 208,845.69 | 895,052.95 | 447,526.47 | [source](https://portal.compraspublicas.gob.ec/sercop/?p=32324) |
| 2017 | 29,835,098,320.79 | 5,967.02 | 59,670.20 | 447,526.47 | 208,845.69 | 895,052.95 | 447,526.47 | [source](https://portal.compraspublicas.gob.ec/sercop/?p=32328) |
| 2018 | 34,853,371,653.72 | 6,970.67 | 69,706.74 | 522,800.57 | 243,973.60 | 1,045,601.15 | 522,800.57 | [source](https://portal.compraspublicas.gob.ec/sercop/?p=32334) |
| 2019 | 35,529,394,461.72 | 7,105.88 | 71,058.79 | 532,940.92 | 248,705.76 | 1,065,881.83 | 532,940.92 | [source](https://portal.compraspublicas.gob.ec/sercop/?p=35906) |
| 2020 | 35,498,420,637.20 | 7,099.68 | 70,996.84 | 532,476.31 | 248,488.94 | 1,064,952.62 | 532,476.31 | [source](https://portal.compraspublicas.gob.ec/sercop/?p=39607) |
| 2021 | 32,080,363,387.48 | 6,416.07 | 64,160.73 | 481,205.45 | 224,562.54 | 962,410.90 | 481,205.45 | [source](https://portal.compraspublicas.gob.ec/sercop/montos-de-contratacion-publica-2021/) |
| 2022 | 33,899,734,759.85 | 6,779.95 | 67,799.47 | 508,496.02 | 237,298.14 | 1,016,992.04 | 508,496.02 | [source](https://portal.compraspublicas.gob.ec/sercop/wp-content/uploads/2022/01/montos_contratacion_2022-2-1.pdf) |
| 2023 | 31,502,865,593.76 | 6,300.57 | 63,005.73 | 472,542.98 | 220,520.06 | 945,085.97 | 472,542.98 | [source](https://portal.compraspublicas.gob.ec/sercop/wp-content/uploads/2023/01/montos_contratacion_2023.pdf) |
| 2024 | 33,296,819,775.31 | 6,659.36 | 66,593.64 | 499,452.30 | 233,077.74 | 998,904.59 | 499,452.30 | [source](https://portal.compraspublicas.gob.ec/sercop/wp-content/uploads/2024/01/montos_contratacion_2024.pdf) |
| 2026 | 46,255,572,824.33 | 10,000.00 (ínfima / subasta inversa / licitación) | - | - | - | 10,000.00 (ínfima / licitación) | 10,000.00 (ínfima / concurso) | [source](https://portal.compraspublicas.gob.ec/sercop/wp-content/uploads/2026/01/INFOGRAFIA-MONTOS-2026-01.png) |

How each year was verified:

- 2018, 2021, 2023, 2024 and 2026: figures read directly from the cited source by this task (2023 and 2024 PDF text; 2018 and 2021 page text; the 2026 image read visually: PIE 46.255.572.824,33 and "Menor o igual a $10.000,00" / "Mayor a $10.000,00").
- 2015, 2016, 2017, 2019, 2020: page text read through a summarising fetch tool (SERCOP blocks plain downloads of these pages and they link no PDF); PIE, ínfima and menor-cuantía figures were re-read and match the arithmetic. The works and cotización-upper figures were checked only through the arithmetic. Treat these five as verified from the official page with that limitation.
- 2022: PDF text read (ínfima 6,779.95, menor cuantía 67,799.47, cotización up to 508,496.02, works 237,298.14 and 1,016,992.04); the PIE was taken from the same PDF by the research step.
- 2016 and 2017: SERCOP prints the same PIE (29,835,098,320.79) in both years.
- Typos on SERCOP's own pages (for example a works "precio fijo" figure printed as 36.317.117,01 for 2015, and a 2016/2017 works cotización lower bound of 208.052,95 against a menor-cuantía bound of 208.845,69) were not used; the coefficient arithmetic is used instead and agrees with the other printed figures.

## Years not used

- **2025: excluded.** The year has two published regimes. SERCOP's January 2025 table (xlsx, PIE 36.063.017.083,08) uses the coefficients above (ínfima 7,212.60; menor cuantía 72,126.03; cotización up to 540,945.26). After the Ley Orgánica de Integridad Pública (Registro Oficial Tercer Suplemento 68, 26 June 2025) SERCOP's resolution R.E-SERCOP-2025-0152 sets new amounts that applied in its tools from 1 August 2025 (ínfima, subasta inversa, licitación and concurso público at USD 10,000), see https://portal.compraspublicas.gob.ec/sercop/wp-content/uploads/2025/06/R.E-SERCOP-2025-0152-signed-signed.pdf. The year is left out rather than mixed. Which thresholds applied between 3 and 7 October 2025 is not documented in any source read here and is **unverified**.
- **2026: used, but cannot be analysed for bunching.** Every threshold is USD 10,000 and the procedure below it (ínfima cuantía) is not in the open data.

## The October 2025 reform

Verified from SERCOP documents: the Constitutional Court declared the Ley Orgánica de Integridad Pública unconstitutional in form (as annotated in the SERCOP-hosted LOSNCP text, Registro Oficial Constitucional 96, 3 October 2025; the court's own ruling was not read in full), and the Ley Orgánica Reformatoria a la LOSNCP was published in Registro Oficial Cuarto Suplemento 140 on 7 October 2025 (SERCOP resolution R.E-SERCOP-2025-0154, https://portal.compraspublicas.gob.ec/sercop/wp-content/uploads/2025/11/Resolucio%CC%81n_re%CC%81gimen_de_transicio%CC%81n_20-11-2025-signed-signed-signed-signed-signed-signed-signed-signed-signed.pdf). In the SERCOP-hosted consolidated law the threshold articles (ínfima cuantía, subasta inversa electrónica, licitación, concurso público) use USD 10,000, and the names menor cuantía, cotización, lista corta and consultancy direct hiring no longer appear as threshold procedures (not an exhaustive text search). The 0.000007 and 0.000002 coefficients survive only in other articles (contratación integral por precio fijo; guarantee exemption). The 2026 infographics apply USD 10,000. Not verified: the Registro Oficial original, Decreto Ejecutivo 193 (general regulation, 28 October 2025) beyond its citation in the SERCOP resolution, and any change after February 2026.
