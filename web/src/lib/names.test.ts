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
  ["DIRECCIÓN DISTRITAL 10D01-IBARRA-PIMAMPIRO-SAN MIGUEL DE URCUQUÍ-MTOP", "Dirección Distrital 10D01-Ibarra-Pimampiro-San Miguel de Urcuquí-MTOP"],
  ["PILEGGI CONSTRUCCIONES C.LTDA.", "Pileggi Construcciones C.LTDA."],
  ["EMPRESA PUBLICA UNIDAD NACIONAL DE ALMACENAMIENTO UNA EP", "Empresa Publica Unidad Nacional de Almacenamiento Una EP"],
];

for (const [input, expected] of CASES) {
  test(`displayName: ${input.slice(0, 48)}`, () => assert.equal(displayName(input), expected));
}

test("mixed-case text is untouched", () => assert.equal(displayName("Constructora Andina Cía. Ltda."), "Constructora Andina Cía. Ltda."));
test("identifiers with digits are untouched", () => assert.equal(displayName("0791755964001"), "0791755964001"));
test("empty values", () => assert.equal(displayName(null), ""));
test("isAllCaps ignores very short text", () => assert.equal(isAllCaps("EP"), false));
