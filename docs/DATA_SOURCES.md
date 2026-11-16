# Data sources

All data is public and was retrieved on **2026-11-16**. Only official government hosts are used
(`www.sri.gob.ec`, `descargas.sri.gob.ec`, `appscvsmovil.supercias.gob.ec`); the downloader refuses
any other host. Raw files live under `data/raw/` (git-ignored); derived tables under `data/lake/`.

Licence/terms: only text actually read on a publisher page is quoted. "Not stated" means no licence
or terms-of-use text was found on the page or file listing consulted. That is not a statement that
reuse is unrestricted.

## 1. SERCOP open contracting data (OCDS)

| Item | Value |
|---|---|
| Publisher | SERCOP (Servicio Nacional de Contratación Pública) |
| Obtained from | Open Contracting Data Registry: https://data.open-contracting.org/en/publication/110 |
| Licence | CC BY 3.0 EC |
| Retrieved | 2026-11-16 |
| Size | 2,251,027 processes |
| Local file | `data/raw/sercop_ocds_full.jsonl.gz` -> `processes`, `tenderers`, `awards` tables (`veedor lake build`) |

## 2. SRI RUC registry (taxpayer open data)

| Item | Value |
|---|---|
| Publisher | SRI (Servicio de Rentas Internas) |
| Listing page | https://www.sri.gob.ec/datasets |
| Files | 24 per-province zips, e.g. https://descargas.sri.gob.ec/download/datosAbiertos/SRI_RUC_Galapagos.zip. The list is discovered from the page at download time, not hard-coded. Provinces: Azuay, Bolivar, Carchi, Cañar, Chimborazo, Cotopaxi, El Oro, Esmeraldas, Galapagos, Guayas, Imbabura, Loja, Los Rios, Manabi, Morona Santiago, Napo, Orellana, Pastaza, Pichincha, Santa Elena, Santo Domingo, Sucumbios, Tungurahua, Zamora Chinchipe |
| Data dictionary | https://www.sri.gob.ec/o/sri-portlet-biblioteca-alfresco-internet/descargar/b7b22e05-84cc-4de0-8ec7-6b0537b0a1e2/SRI_RUC_DD.xlsx (linked from the page, not parsed) |
| Licence/terms | Not stated on the listing page |
| Retrieved | 2026-11-16 (server `Last-Modified` for Galapagos: 2026-11-01) |
| Format (verified from the files) | `\|`-delimited, header row, double-quote quoting (names may contain `\|` and `""`), 21 columns identical in all 24 files, UTF-8 (the loader checks every file and falls back to Latin-1 if a file is not valid UTF-8). One row per establishment. |
| Output | `data/lake/suppliers_sri.parquet` |

Column mapping (`suppliers_sri`):

| Output | Source column |
|---|---|
| `ruc` | `NUMERO_RUC` |
| `legal_name` | `RAZON_SOCIAL` |
| `status` | `ESTADO_CONTRIBUYENTE` (`ACTIVO`, `PASIVO`, `SUSPENDIDO`) |
| `taxpayer_type` | `TIPO_CONTRIBUYENTE` (`PERSONA NATURAL`, `SOCIEDAD`) |
| `activity_start_date` | `FECHA_INICIO_ACTIVIDADES` -> `YYYY-MM-DD` |
| `suspension_date` | `FECHA_SUSPENSION_DEFINITIVA` -> `YYYY-MM-DD` |
| `restart_date` | `FECHA_REINICIO_ACTIVIDADES` -> `YYYY-MM-DD` |
| `ciiu_code` | `CODIGO_CIIU` |
| `activity` | `ACTIVIDAD_ECONOMICA` |
| `province` | `DESCRIPCION_PROVINCIA_EST` (of the retained establishment) |
| `source_file` | name of the zip the row came from |

Processing rules: rows are filtered to RUCs present in `awards.parquet` or `tenderers.parquet`; one
row is kept per RUC (the lowest `NUMERO_ESTABLECIMIENTO`, i.e. the head establishment); empty strings
become NULL.

Caveats:
- **Status is current status**, as of the file's publication, not status at award time. Do not read
  `status` or `suspension_date` as the situation when a contract was awarded.
- A RUC appears in the file of every province where it has an establishment; `province` is the
  province of the retained establishment only.
- Dates are reported as published. The earliest `activity_start_date` in the filtered table is
  `1541-01-06`, which is a source value, not a real start date; consumers must treat implausible
  dates as unreliable.
- Absence from the registry means the RUC was not found in these files, nothing more.

## 3. SRI "empresas fantasmas" catalogue

| Item | Value |
|---|---|
| Publisher | SRI |
| Listing page | https://www.sri.gob.ec/datasets (section "Empresas Fantasmas", entry `SRI_CATASTRO_EMPRESAS_FANTASMAS`) |
| File URL | https://www.sri.gob.ec/o/sri-portlet-biblioteca-alfresco-internet/descargar/909ad236-f46c-488f-8661-f2f4e5faf1c4/SRI_Catastro_Empresas_Fantasmas.csv |
| Dictionary | https://www.sri.gob.ec/o/sri-portlet-biblioteca-alfresco-internet/descargar/3ba85ea0-69b3-48d6-b77d-e286966e4107/SRI_CATASTRO_EMPRESAS_FANTASMAS_DD.xlsx (linked, not parsed) |
| Licence/terms | Not stated on the listing page |
| Retrieved | 2026-11-16 |
| Format (verified) | `\|`-delimited, ISO-8859-1 (Latin-1), CRLF, 21 columns; the header has a leading space in ` RAZON_SOCIAL`. A few records are wrapped in an extra pair of quotes and some have embedded newlines; the loader re-parses them. Dates are Excel day serials (origin 1899-12-30). |
| Output | `data/lake/ghost_companies.parquet` (1,113 rows, 1,113 distinct RUCs) |

Column mapping: `ruc` = `NUMERO_RUC`; `legal_name` = `RAZON_SOCIAL`; `resolution` =
`RESOLUCION_CALIFICACION`; `notification_date` = `FECHA_NOTIFICACION_RESOLUCION` (serial converted to
`YYYY-MM-DD`); `taxpayer_type` = `TIPO_CONTRIBUYENTE`; `qualification_detail` =
`DETALLE_CALIFICACION`; `ruc_status` = `ESTADO_RUC`; `challenge_state` = `ESTADO_IMPUGNACIÓN`;
`source_file`.

Deviation from the contract: the contract lists `publication_date`. The source has **no publication
date**, so the column exists but is always NULL; `notification_date` (date the SRI notified the
qualification resolution) is the closest real field. The table also carries extra columns not in the
contract (`taxpayer_type`, `qualification_detail`, `ruc_status`, `challenge_state`, `notification_date`).

Caveats:
- This is the SRI's published qualification list. Qualification can be challenged: `challenge_state`
  shows 78 rows "FINALIZADO SE RATIFICA COMO FANTASMA", 14 "FINALIZADO SE RATIFICA CALIFICACIÓN POR
  PERÍODOS", and 986 with "-" (no challenge recorded); the remainder are pending or other states. 33
  rows currently have `ruc_status` = `ACTIVO`. A listing is a registry fact, not a finding about any
  contract.
- The file is a snapshot; it is not a history of qualifications and reactivations.

## 4. Superintendencia de Compañías, Valores y Seguros: directory and financials

| Item | Value |
|---|---|
| Publisher | Superintendencia de Compañías, Valores y Seguros (Ecuador) |
| Directory | https://appscvsmovil.supercias.gob.ec/ranking/recursos/bi_compania.csv |
| Financials | https://appscvsmovil.supercias.gob.ec/ranking/recursos/bi_ranking.csv |
| Licence/terms | Not stated. The `/ranking/` landing page returned HTTP 403 to automated retrieval, so no terms text could be read |
| Retrieved | 2026-11-16 (server `Last-Modified` of `bi_ranking.csv`: 2026-11-15) |
| Format (verified) | comma-delimited, header row, UTF-8, standard quoting. Directory 348,162 rows; ranking 1,677,415 rows (2008-2025). Text fields in the directory are space-padded; the loader trims them. |

`companies_supercias.parquet` (348,162 rows): `expediente` = `expediente`, `ruc` = `ruc`,
`legal_name` = `nombre`, `company_type` = `tipo`, `province` = `provincia`. Not unique by RUC: 152
RUCs are shared by more than one `expediente`, and some RUCs are placeholders (e.g. `1700000000005`).

`company_financials.parquet` (1,662,983 rows): the ranking file has no RUC, so it is joined to the
directory on `expediente`; rows whose `expediente` is not in the directory or has no RUC are dropped.

| Output | Source column |
|---|---|
| `ruc` | `bi_compania.ruc` (via `expediente`) |
| `year` | `anio` |
| `expediente` | `expediente` (extra; keeps rows unique, since (`ruc`, `year`) is not) |
| `revenue` | `ingresos_ventas` (sales revenue) |
| `total_income` | `ingresos_totales` (extra; only present from 2010) |
| `assets` | `activos` |
| `equity` | `patrimonio` |
| `employees` | `n_empleados` |

Caveats:
- `revenue` is `ingresos_ventas`. It is 0.00 in 804,017 of 1,662,983 rows; the zero share is 80-81% in
  2008-2009, 96-99% in 2010-2011 and 28-41% from 2012, which looks like missing data rather than real zero sales. Do not treat zero as
  a measured value without checking the year.
- Only companies supervised by the Superintendencia appear (about 78% of awarded RUCs that belong to
  companies, third digit 9, were found). Natural persons and most public entities are absent.
- The ranking file contains many further ratio columns (liquidity, leverage, margins); they are not
  loaded.

## Match rates against the lake (2026-11-16)

Distinct supplier RUCs in `awards.parquet` or `tenderers.parquet`: 90,893. Distinct awarded RUCs:
68,587.

| Table | Matched |
|---|---|
| `suppliers_sri` (any lake RUC) | 90,888 of 90,893 (99.99%) |
| `suppliers_sri` (awarded RUCs) | 68,584 of 68,587 |
| `companies_supercias` (any lake RUC) | 21,395 of 90,893 (23.54%) |
| `companies_supercias` (awarded RUCs) | 15,402 of 68,587 (22.5%; 15,401 of 19,847 company RUCs) |
| `company_financials` (awarded RUCs) | 15,109 of 68,587 |
| `ghost_companies` (awarded RUCs) | 16 of 68,587 |

## Reproduce

```
uv run veedor registries download   # SRI zips + ghost CSV + Supercias CSVs (skips complete files)
uv run veedor registries load       # build the Parquet tables (needs awards/tenderers in the lake)
uv run veedor registries status     # row counts per table
```
