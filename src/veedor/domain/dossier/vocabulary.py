"""Closed vocabularies of the dossier layer: section titles, fixed terms, forbidden wording."""

from __future__ import annotations

import re

SECTION_WHAT = "Qué se contrató"
SECTION_SIGNALS = "Señales detectadas"
SECTION_REGISTRAL = "Contexto registral"
SECTION_WINNER = "Proveedor adjudicado"
SECTION_RELATION = "Relación entidad–proveedor"
SECTION_CONTEXT = "Contexto comparativo"
SECTION_LIMITS = "Limitaciones y cómo verificar"

SECTION_TITLES: tuple[str, ...] = (
    SECTION_WHAT,
    SECTION_SIGNALS,
    SECTION_REGISTRAL,
    SECTION_WINNER,
    SECTION_RELATION,
    SECTION_CONTEXT,
    SECTION_LIMITS,
)

NOT_AVAILABLE = "no disponible"

# Fixed proper nouns and acronyms that are not data about a process; always allowed as names.
STATIC_TERMS: tuple[str, ...] = (
    "Ecuador",
    "Veedor",
    "SRI",
    "Servicio de Rentas Internas",
    "SERCOP",
    "Servicio Nacional de Contratación Pública",
    "OCDS",
    "RUC",
    "USD",
    "CPC",
    "CIIU",
    "Superintendencia de Compañías",
    "Persona natural",
    *SECTION_TITLES,
)

# Numbers that are part of the product, not of a process (scale of the risk score).
STATIC_NUMBERS: tuple[int, ...] = (100,)

# Capitalised only because they open a sentence; ignored when they stand alone at sentence start.
SENTENCE_STARTERS: frozenset[str] = frozenset(
    {
        "El",
        "La",
        "Los",
        "Las",
        "Un",
        "Una",
        "Unos",
        "Unas",
        "Lo",
        "Al",
        "Del",
        "De",
        "En",
        "Se",
        "Su",
        "Sus",
        "Este",
        "Esta",
        "Estos",
        "Estas",
        "Esto",
        "Ese",
        "Esa",
        "Por",
        "Para",
        "Con",
        "Sin",
        "Según",
        "Entre",
        "Desde",
        "Durante",
        "Hasta",
        "Sobre",
        "Ante",
        "Tras",
        "Además",
        "También",
        "Asimismo",
        "Cabe",
        "No",
        "Si",
        "Sí",
        "Como",
        "Cuando",
        "Donde",
        "Dado",
        "Dada",
        "Ningún",
        "Ninguna",
        "Ninguno",
        "Hay",
        "Existe",
        "Existen",
        "Fue",
        "Fueron",
        "Ha",
        "Han",
        "Es",
        "Son",
        "Aunque",
        "Mientras",
        "Pero",
        "Y",
        "O",
        "A",
        "Cada",
        "Todos",
        "Todas",
        "Solo",
        "Sólo",
        "Únicamente",
        "Actualmente",
        "Finalmente",
        "Adicionalmente",
        "Respecto",
        "Contexto",
        "Proceso",
        "Procesos",
        "Contratación",
        "Adjudicación",
        "Señal",
        "Señales",
        "Indicador",
        "Indicadores",
        "Proveedor",
        "Entidad",
        "Presupuesto",
        "Monto",
        "Oferentes",
        "Oferente",
        "Objeto",
        "Procedimiento",
        "Evidencia",
        "Valor",
        "Umbral",
        "Fecha",
        "Fechas",
        "Código",
        "Limitaciones",
        "Estado",
        "Categoría",
        "Actividad",
        "Provincia",
        "Registro",
        "Listado",
        "Antes",
        "Después",
        "Primera",
        "Primero",
        "Última",
        "Último",
        "Mediana",
        "Proporción",
        "Relación",
        "Resumen",
        "Nota",
        "Verificación",
        "Dichos",
        "Dicho",
        "Tipo",
        "Inicio",
        "Hubo",
        "Depende",
        "Compara",
        "Dossier",
        "Dato",
        "Datos",
        "Otra",
        "Otro",
        "Otras",
        "Otros",
        "Número",
        "Historial",
        "Estadísticas",
        "Ingresos",
        "Puntaje",
    }
)

# Wording that asserts wrongdoing. Matched on accent-folded, lowercased text at word starts.
FORBIDDEN_PATTERN = re.compile(
    r"\b(?:corrupt\w*|corrupci\w*|corromp\w*|fraud\w*|defraud\w*|irregular\w*|culpab\w*|culpa|ilegal\w*"
    r"|ilicit\w*|ilegitim\w*|delit\w*|delict\w*|delincuen\w*|estaf\w*|soborn\w*|cohecho\w*|colusi\w*"
    r"|coluded\w*|malvers\w*|peculad\w*|prevaric\w*|concusi\w*|robo|robos|ladron\w*|sobreprecio\w*"
    r"|criminal\w*|acusa\w*|mafia\w*|coima\w*|desfalco\w*|trampa\w*|tramposo\w*|amana\w*|amanad\w*"
    r"|direccionad\w*|dirigid[oa]s? a favor|testaferr\w*|lavado de (?:activos|dinero|capitales)"
    r"|cartel\w*|nepotism\w*|empresas? de papel|empresas? pantalla|favorec\w* indebid\w*|indebid\w*"
    r"|acuerdos? previos?|trafico de influencia\w*|enriquecimiento ilicit\w*|extors\w*|chantaj\w*"
    r"|conspir\w*|complic\w*|ganancias? ilicit\w*)\b"
)

# Inference and intensifier wording: a dossier lists facts, it does not conclude or insist.
INFERENCE_PATTERN = re.compile(
    r"\b(?:por lo tanto|por ende|en consecuencia|se concluye|concluy\w*|se deduce|se infiere|demuestra\w*"
    r"|prueba que|confirma que|evidencia que|queda claro|es evidente|evidentemente|claramente|obviamente"
    r"|sin duda|con creces|de manera sospechosa|sospechos\w*|escandalos\w*|alarmante\w*)\b"
)

# Matches look-alike, hidden or markup characters that never belong in a Spanish dossier.
HIDDEN_CHARS = re.compile("[\u00ad\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069\ufeff]")
NON_LATIN_LETTERS = re.compile("[\u0370-\u03ff\u0400-\u052f\uff00-\uffef]")
MARKUP = re.compile(r"<\s*/?\s*[a-zA-Z!][^>]*>|\]\s*\(|javascript:|data:text|&#?\w+;|`{2,}", re.IGNORECASE)

MONTHS_ES: tuple[str, ...] = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
    "octubre", "noviembre", "diciembre",
)  # fmt: skip

# Spanish number words checked like digits (exact match against pack numbers). "un/uno/una" are
# not checked: they are articles as often as numerals.
NUMBER_WORDS: dict[str, int] = {
    "cero": 0, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8,
    "nueve": 9, "diez": 10, "once": 11, "doce": 12, "trece": 13, "catorce": 14, "quince": 15,
    "dieciseis": 16, "diecisiete": 17, "dieciocho": 18, "diecinueve": 19, "veinte": 20,
    "treinta": 30, "cuarenta": 40, "cincuenta": 50, "sesenta": 60, "setenta": 70, "ochenta": 80,
    "noventa": 90, "cien": 100,
}  # fmt: skip

# Function words (articles, determiners, prepositions, conjunctions, quantifiers). A capitalised
# one is never a name, wherever it stands, so it is stripped from the start of a name span.
FUNCTION_WORDS: frozenset[str] = frozenset(
    {
        "El", "La", "Los", "Las", "Un", "Una", "Unos", "Unas", "Lo", "Al", "Del", "De", "En", "Se",
        "Su", "Sus", "Este", "Esta", "Estos", "Estas", "Esto", "Ese", "Esa", "Esos", "Esas", "Por",
        "Para", "Con", "Sin", "Según", "Entre", "Desde", "Durante", "Hasta", "Sobre", "Ante", "Tras",
        "Como", "Cuando", "Donde", "Y", "E", "O", "U", "A", "Ambos", "Ambas", "Cada", "Todos", "Todas",
        "Aunque", "Mientras", "Pero", "Si", "Sí", "No", "También", "Además", "Asimismo", "Ningún",
        "Ninguna", "Ninguno", "Otro", "Otra", "Otros", "Otras", "Dicho", "Dicha", "Dichos", "Dichas",
        "Mismo", "Misma", "Solo", "Sólo", "Únicamente", "Cuyo", "Cuya", "Cual", "Que", "Qué",
    }
)  # fmt: skip

# Ordinary sentence-opening words that are not function words: report verbs and nouns. They are
# ignored only when they stand alone at the start of a sentence. The list is closed on purpose:
# an unknown capitalised word there (an invented company name) is still reported.
SENTENCE_STARTERS = SENTENCE_STARTERS | frozenset(
    {
        "Consta", "Constan", "Figura", "Figuran", "Registra", "Registran", "Presenta", "Presentan",
        "Indica", "Indican", "Muestra", "Muestran", "Corresponde", "Corresponden", "Resulta",
        "Resultan", "Aparece", "Aparecen", "Participó", "Participaron", "Recibió", "Recibieron",
        "Adjudicó", "Adjudicaron", "Obtuvo", "Obtuvieron", "Destaca", "Destacan", "Cuenta", "Cuentan",
        "Tiene", "Tienen", "Posee", "Poseen", "Cumple", "Cumplen", "Supera", "Superan", "Alcanza",
        "Equivale", "Equivalen", "Representa", "Representan", "Señala", "Señalan", "Informa",
        "Informan", "Establece", "Establecen", "Detalla", "Detallan", "Describe", "Describen",
        "Incluye", "Incluyen", "Contrató", "Contrataron", "Convocó", "Convocaron", "Suscribió",
        "Pertenece", "Pertenecen", "Estuvo", "Estuvieron", "Habría", "Hay", "Había", "Fueron",
        "Entonces", "Luego", "Posteriormente", "Anteriormente", "Igualmente", "Asimismo", "Ahora",
        "Dicho", "Respecto", "Referente", "Conforme", "Mediante", "Adicionalmente", "Cabe", "Nótese",
        "Importante", "Atención", "Aclaración", "Observación", "Conclusión", "Hallazgo", "Hallazgos",
        "Situación", "Datos", "Dato", "Resultado", "Resultados", "Análisis", "Información", "Fuente",
        "Fuentes", "Verifique", "Verificar", "Consulte", "Revise", "Compare",
    }
)  # fmt: skip

# Context signals are informational (weight 0). A listing published after the process is also
# informational, whatever code the marts use for it.
CONTEXT_SIGNAL_CODES: frozenset[str] = frozenset(
    {"GHOST_COMPANY_LISTED_LATER", "CONTRACT_VS_COMPANY_SIZE_SAME_YEAR"}
)
