/**
 * Plain-Spanish explanations for each signal, shown next to the facts the API returns.
 * "why" says why the pattern can deserve a second look; "normal" says how it can be perfectly ordinary.
 * Both follow docs/METHODOLOGY.md (rule and false-positive notes) and never assert wrongdoing.
 */
export interface SignalCopy {
  why: string;
  normal: string;
}

export const SIGNAL_COPY: Record<string, SignalCopy> = {
  SINGLE_BIDDER: {
    why: "Con una sola oferta no hubo competencia de precios, y sin ella es más difícil saber si el Estado pagó un buen precio.",
    normal: "Hay proveedores que son los únicos distribuidores o fabricantes de lo que se compró, y hay mercados locales con muy pocas empresas.",
  },
  SHORT_TENDER_WINDOW: {
    why: "Un plazo corto da menos tiempo a otras empresas para preparar su oferta y puede reducir la competencia.",
    normal: "El plazo mínimo legal cambia según el objeto y el monto, hay compras urgentes legítimas, y una fecha puede estar mal registrada.",
  },
  LOW_SAVING: {
    why: "Cuando se adjudica casi exactamente el presupuesto, no hubo rebaja: conviene mirar si hubo competencia real.",
    normal: "Si el presupuesto salió de cotizaciones de mercado, o el precio es fijo (tarifas reguladas, primas de seguros), no queda espacio para ahorrar.",
  },
  NEW_SUPPLIER: {
    why: "Una empresa muy reciente tiene poca trayectoria que revisar y puede haberse creado para este contrato.",
    normal: "Hay empresas nuevas creadas para un proyecto legítimo, y un RUC nuevo puede ser un negocio que ya existía y cambió su forma legal.",
  },
  SUPPLIER_NOT_ACTIVE: {
    why: "Un proveedor que no figura como activo en el SRI plantea la duda de si podía contratar con el Estado.",
    normal: "El estado que se muestra es el de hoy, no el que tenía cuando ganó: pudo suspenderse después sin ningún problema en este proceso.",
  },
  GHOST_COMPANY_LIST: {
    why: "El SRI publicó que esta empresa figura en su listado de contribuyentes con transacciones inexistentes, y ya figuraba cuando se hizo el proceso.",
    normal: "Figurar en el listado es un hecho de registro, no una conclusión sobre este contrato, y la calificación puede haber sido impugnada.",
  },
  GHOST_COMPANY_LISTED_LATER: {
    why: "La empresa figura hoy en el listado del SRI, pero se notificó después del proceso o sin fecha: es solo información de contexto.",
    normal: "La entidad no pudo conocer ese listado cuando contrató, por eso no suma puntos.",
  },
  BUYER_CONCENTRATION: {
    why: "Cuando un solo proveedor recibe buena parte de lo que adjudica una entidad en un año, conviene mirar cómo se repartieron los contratos.",
    normal: "Hay entidades que dependen de un único proveedor (servicios básicos, obras divididas en contratos) y entidades pequeñas con pocas compras.",
  },
  REPEATED_DIRECT_AWARDS: {
    why: "Adjudicar varias veces seguidas al mismo proveedor, sin competencia, deja de lado a otras empresas que podrían ofrecer lo mismo.",
    normal: "Servicios recurrentes como mantenimiento, comunicaciones o asesoría se contratan por partes, y a veces hay un único proveedor posible.",
  },
  RECURRING_COBIDDERS: {
    why: "Si las mismas dos empresas se enfrentan una y otra vez, conviene revisar si la competencia entre ellas es real.",
    normal: "En mercados locales con pocos proveedores es natural que se encuentren a menudo, igual que negocios asociados que trabajan en el mismo rubro.",
  },
  CONTRACT_VS_COMPANY_SIZE: {
    why: "Un contrato mucho mayor que lo que la empresa vendió el año anterior hace dudar de si tiene capacidad para cumplirlo.",
    normal: "Puede compararse con un año pequeño y atípico; los consorcios y las constructoras tienen ingresos irregulares, y el monto puede cubrir varios años.",
  },
  CONTRACT_VS_COMPANY_SIZE_SAME_YEAR: {
    why: "El contrato supera tres veces los ingresos que la empresa reportó ese mismo año. Es solo contexto de menor confianza.",
    normal: "Los ingresos del mismo año pueden incluir el propio contrato, por eso esta comparación no suma puntos.",
  },
};

export const FALLBACK_COPY: SignalCopy = {
  why: "La regla marcó un patrón atípico respecto a procesos comparables.",
  normal: "Un patrón atípico puede tener explicaciones legítimas: la revisión humana lo decide.",
};

/**
 * Short names for tables, where the full label from the API would take three lines. The API sends only the long
 * `label_es`, so these are written here: neutral, same meaning, never more specific than the rule. The full label stays
 * available as the tooltip and to screen readers (see SignalChips).
 */
export const SHORT_LABEL: Record<string, string> = {
  SINGLE_BIDDER: "Oferente único",
  SHORT_TENDER_WINDOW: "Plazo corto",
  LOW_SAVING: "Ahorro bajo",
  NEW_SUPPLIER: "Proveedor reciente",
  SUPPLIER_NOT_ACTIVE: "No activo en el SRI",
  GHOST_COMPANY_LIST: "En el listado del SRI",
  GHOST_COMPANY_LISTED_LATER: "Listado del SRI posterior",
  BUYER_CONCENTRATION: "Concentración en un proveedor",
  REPEATED_DIRECT_AWARDS: "Directas repetidas",
  RECURRING_COBIDDERS: "Mismos oferentes",
  CONTRACT_VS_COMPANY_SIZE: "Contrato grande para la empresa",
  CONTRACT_VS_COMPANY_SIZE_SAME_YEAR: "Contrato grande, mismo año",
};

/** Short label for a signal code; falls back to the API label (or the code) for a signal this table does not know. */
export const shortLabel = (code: string, labels: Record<string, string>): string => SHORT_LABEL[code] ?? labels[code] ?? code;
