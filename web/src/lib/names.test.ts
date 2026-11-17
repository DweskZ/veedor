import assert from "node:assert/strict";
import { test } from "node:test";
import { displayName, isAllCaps } from "./names.ts";

const CASES: [string, string][] = [
  ["GOBIERNO AUTONOMO DESCENTRALIZADO PARROQUIAL RURAL DE SANTA CECILIA", "Gobierno Autonomo Descentralizado Parroquial Rural de Santa Cecilia"],
  ["MUNICIPIO DEL CANTON PASAJE", "Municipio del Canton Pasaje"],
  ["MERPALCEV CIA. LTDA.", "Merpalcev CIA. LTDA."],
  ["EMPRESA PUBLICA MUNICIPAL DE AGUA POTABLE Y ALCANTARILLADO EP", "Empresa Publica Municipal de Agua Potable y Alcantarillado EP"],
  ["INSTITUTO ECUATORIANO DE SEGURIDAD SOCIAL IESS", "Instituto Ecuatoriano de Seguridad Social IESS"],
  ["GAD MUNICIPAL DEL CANTÓN LAGO AGRIO", "GAD Municipal del Cantón Lago Agrio"],
  ["CONSTRUCTORA DEL SUR S.A.", "Constructora del Sur S.A."],
  ["ADECENTAMIENTO DEL COLISEO, CERRAMIENTO Y CASA COMUNAL, PARROQUIA DE SANTA CECILIA-CANTÓN LAGO AGRIO", "Adecentamiento del Coliseo, Cerramiento y Casa Comunal, Parroquia de Santa Cecilia-Cantón Lago Agrio"],
  ["UNIDAD EDUCATIVA FISCAL N° 12 JOSÉ MARÍA VELASCO", "Unidad Educativa Fiscal N° 12 José María Velasco"],
  ["HOSPITAL GENERAL IESS DE QUITO", "Hospital General IESS de Quito"],
  ["PETROLEOS Y SERVICIOS C.A.", "Petroleos y Servicios C.A."],
  ["Ministerio de Salud Pública", "Ministerio de Salud Pública"],
  ["DIRECCIÓN DISTRITAL 10D01-IBARRA-PIMAMPIRO-SAN MIGUEL DE URCUQUÍ-MTOP", "Dirección Distrital 10D01-IBARRA-PIMAMPIRO-SAN Miguel de Urcuquí-MTOP"],
  ["PILEGGI CONSTRUCCIONES C.LTDA.", "Pileggi Construcciones C.LTDA."],
  ["EMPRESA PUBLICA UNIDAD NACIONAL DE ALMACENAMIENTO UNA EP", "Empresa Publica Unidad Nacional de Almacenamiento Una EP"],
  // Real names (SERCOP buyers). A word after a dash or parenthesis is never lower-cased; known acronyms stay; accents are never added.
  ["DIRECCION DISTRITAL 22D01- LA JOYA DE LOS SACHAS-SALUD", "Direccion Distrital 22D01- La Joya de los Sachas-Salud"],
  // Identifiers inside names stay as published; short technical acronyms stay in capitals.
  ["SIE-GADMB-2021-20973 ADQUISICION DE UNIFORMES", "SIE-GADMB-2021-20973 Adquisicion de Uniformes"],
  ["LICITACION LICO-GADPP-2022-004 CONSTRUCCION DE PUENTE", "Licitacion LICO-GADPP-2022-004 Construccion de Puente"],
  ["CONTRATACION DE SERVICIOS SEGUN RUC 1790012345001 DEL PROVEEDOR", "Contratacion de Servicios Segun RUC 1790012345001 del Proveedor"],
  ["RUC DEL PROVEEDOR Y CODIGO CPC 4571001", "RUC del Proveedor y Codigo CPC 4571001"],
  ["PAGO DEL IVA Y USD 12.500,00 POR CONTRATO NIC-EP-2020-0145", "Pago del IVA y USD 12.500,00 por Contrato NIC-EP-2020-0145"],
  ["REGIMEN ESPECIAL RE-GADMC-2023-045 ADQUISICION DE MEDICINAS", "Regimen Especial RE-GADMC-2023-045 Adquisicion de Medicinas"],
  ["CATALOGO ELECTRONICO CE-20210000987 DE INSUMOS", "Catalogo Electronico CE-20210000987 de Insumos"],
  ["EMPRESA 0991234567001-CIA. LTDA. BAJO RESOLUCION 2019-0034", "Empresa 0991234567001-CIA. LTDA. Bajo Resolucion 2019-0034"],
  ["DIRECCION DISTRITAL 17D12 - PEDRO VICENTE MALDONADO - PUERTO QUITO - SAN MIGUEL DE LOS BANCOS  - SALUD", "Direccion Distrital 17D12 - Pedro Vicente Maldonado - Puerto Quito - San Miguel de los Bancos  - Salud"],
  ["GOBIERNO PROVINCIAL DE LOS RIOS", "Gobierno Provincial de Los Rios"],
  ["SALUD - LOS RIOS", "Salud - Los Rios"],
  ["HOSPITAL BASICO (LOS BANCOS) - DEL IESS", "Hospital Basico (Los Bancos) - Del IESS"],
  ["HOSPITAL GENERAL DEL NORTE DE GUAYAQUIL LOS CEIBOS", "Hospital General del Norte de Guayaquil Los Ceibos"],
  ["DIGMAT", "DIGMAT"],
  ["CARRERA DE INGENIERIA AGROPECUARIA IASA I - ESPE", "Carrera de Ingenieria Agropecuaria IASA I - ESPE"],
  ["ASTILLEROS NAVALES ECUATORIANOS - ASTINAVE EP -", "Astilleros Navales Ecuatorianos - ASTINAVE EP -"],
  ["CENTRO DE SALUD A - LOS ESTEROS", "Centro de Salud A - Los Esteros"],
  ["AGENCIA Y/O CONSORCIO DIGMAT-EP", "Agencia y/o Consorcio DIGMAT-EP"],
  ["CONSEJO NACIONAL ELECTORAL DELEGACION DE LOS RIOS", "Consejo Nacional Electoral Delegacion de Los Rios"],
  ["UNIDAD DE EQUITACION Y REMONTA SANTA ANA DE LOS CUATRO RIOS", "Unidad de Equitacion y Remonta Santa Ana de los Cuatro Rios"],
];

for (const [input, expected] of CASES) {
  test(`displayName: ${input.slice(0, 48)}`, () => assert.equal(displayName(input), expected));
}

test("mixed-case text is untouched", () => assert.equal(displayName("Constructora Andina Cía. Ltda."), "Constructora Andina Cía. Ltda."));
test("identifiers with digits are untouched", () => assert.equal(displayName("0791755964001"), "0791755964001"));
test("empty values", () => assert.equal(displayName(null), ""));
test("isAllCaps ignores very short text", () => assert.equal(isAllCaps("EP"), false));
