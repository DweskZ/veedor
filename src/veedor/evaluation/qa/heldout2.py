# ruff: noqa: E501
"""Second held-out phrasing set (pure data, written independently of the code under test).

Same structure as the other sets: answerable phrasings per fact type, signal templates, unanswerable
questions, off-topic questions that share one ambiguous word with the procurement domain, comparison
requests and compound questions that join exactly two intents.
"""

from __future__ import annotations

HELDOUT2_ANSWERABLE: dict[str, tuple[str, ...]] = {
    "tenderers": (
        "cuantos le entraron a este concurso", "quienes mas ofertaron aparte del ganador",
        "hubo mas empresas compitiendo o fue solo una", "cuantas firmas quisieron participar", "cuantos rivales tuvo el ganador",
        "se presento alguien mas a postular", "cuantos concursaron en esta compra", "hasta cuando se podia postular al proceso",
        "desde que fecha podian presentarse los interesados", "habia competencia en esta licitacion o nadie mas se animo",
        "cuantos competidores hubo en total", "cuantas ofertas se recibieron al final", "cuando abrieron y cuando cerraron la recepcion de propuestas",
        "cuantos participaron, aparte de la empresa adjudicada", "cuantos postulantes tuvo esta contratacion",
        "en que fechas se podia concursar", "cuantos proovedores se presentaron", "cuantos oferentes compitieron por esto",
    ),
    "amounts": (
        "cual fue el valor final del contrato en dolares", "diferencia entre lo adjudicado y el presupuesto, o sea el sobrecosto en dólares",
        "cuanto era el techo presupuestario de esta compra", "por que valor se firmo", "cuanto dinero publico se comprometio aqui",
        "el monto contratado supera lo presupuestado", "cuanto se ahorro la entidad respecto al presupuesto", "cuanto vale todo el proceso",
        "a cuanto asciende la adjudicacion", "cuanto presupuesto habia reservado la institucion", "cual es la cifra adjudicada, en usd",
        "cuanto fue el valor referencial", "que tan cerca quedo el precio adjudicado del referencial",
    ),
    "winner": (
        "a que empresa le adjudicaron", "dime la razon social del adjudicatario", "quien fue el elegido como proveedor",
        "que firma obtuvo la adjudicacion", "cual compania gano la licitacion", "a nombre de quien quedo el contrato",
        "como se llama la empresa que se adjudico esto", "quien resulto ganadora en este proceso", "quien es el contratista seleccionado",
        "nombre del proveedor que se llevo el proceso", "cual fue la oferta ganadora y de quien era",
    ),
    "entity": (
        "que institucion publica convoco este proceso", "en que canton o provincia queda la entidad que contrata",
        "ruc de la institucion contratante", "quien es el comprador publico aqui", "cual es la entidad que abrio este concurso",
        "de que ministerio o municipio es esta compra", "que organismo lanzo la convocatoria", "cual es el nombre de la entidad contratante",
        "en que ciudad esta la institucion que pidio esto", "que entidad esta detras de este pedido de compra",
        "esta direccionada a una entidad del gobierno central o local",
    ),
    "procedure": (
        "a que tipo de proceso está direccionada la compra", "el estado del trámite está arreglado/cerrado",
        "cual es el tipo de contratacion que se aplico", "esta adjudicado, desierto o en curso", "que modalidad de compra publica fue",
        "se hizo por subasta inversa o por otra via", "en que etapa se encuentra el proceso ahora", "que normativa o procedimiento especial se uso",
        "cual es el estatus actual del proceso", "fue una contratacion directa o un concurso abierto", "como se denomina el tipo de procedimiento",
        "el proceso ya esta finalizado",
    ),
    "award_dates": (
        "cuando fue la adjudicacion oficial", "en que fecha quedo adjudicado el proceso", "que dia se firmo la adjudicación",
        "cuando se notifico al ganador", "fecha en que se resolvio el proceso", "cuando se publico el resultado de la adjudicacion",
        "en que mes se adjudico esta compra", "a que fecha corresponde el contrato", "cuando se formalizo la contratación",
        "que dia le adjudicaron al proveedor", "fecha de firma del contrato",
    ),
    "object": (
        "cual es el objeto del proceso, o sea que adquirieron", "de que va esta contratacion", "que bien o servicio piden en este proceso",
        "descripcion de lo que se compro", "en que consiste el contrato", "para que contrataron",
        "esta dirigido a bienes, obras o servicios", "que se esta comprando en este proceso", "cual es el detalle de lo contratado",
        "resumen de lo que busca contratar la entidad", "que producto o trabajo se adjudico", "que es lo que van a recibir",
    ),
    "cpc": (
        "numero cpc del producto comprado", "cual es el clasificador central de productos de este objeto", "que codigo cpc tiene esta compra",
        "bajo que codigo de clasificacion de productos esta registrado", "dame la clasificación CPC", "el cpc de lo contratado cual es",
        "cual es el codigo de producto segun la clasificacion nacional", "que cpc le asignaron", "codigo cpc asociado al proceso",
        "a que categoria cpc pertenece lo que se contrato", "cpc?", "how is it classified, what is the CPC code",
    ),
    "context_tenderers": (
        "cuantos oferentes tienen los procesos similares en tipico", "en compras de esta clase cuantas empresas ofertan normalmente",
        "numero habitual de participantes en procesos parecidos", "cuantos postulantes hay en promedio en compras del mismo tipo",
        "la mediana de ofertas en procesos comparables", "usualmente cuantos proveedores compiten en estos procedimientos",
        "tipicamente cuantas empresas ofertan por un proceso como este", "que cantidad de oferentes es la normal para este tipo de compra",
        "cuantas ofertas suele recibir un proceso similar", "en casos parecidos, cuantos participan",
        "cual es el numero tipico de competidores en este grupo de procesos",
    ),
    "context_single": (
        "porcentaje de procesos similares con un unico oferente", "cuantas de las compras parecidas tienen solo un participante",
        "en que proporcion de casos comparables nadie mas se presenta", "frecuencia de oferta unica en procesos del mismo tipo",
        "que fraccion de los procesos similares tuvo un solo proveedor", "con que regularidad hay un solo oferente en este tipo de compras",
        "proporcion de procesos comparables sin competencia", "en procesos como este, cuantas veces ofertó una sola empresa",
        "cuan frecuente es el oferente unico en este grupo", "porcentaje de compras equivalentes con un solo postulante",
    ),
    "context_count": (
        "cuantos procesos similares se usaron como referencia", "tamaño de la muestra de procesos comparables", "cuantos procesos parecidos hay en la base de comparacion",
        "numero de procesos con los que se contrasta esta compra", "cuantas compras del mismo tipo y año entran en la comparacion",
        "cuantas observaciones hay en el grupo de comparacion", "de cuantos procesos similares salen las estadisticas",
        "cantidad de procesos comparables", "que tan amplia es la base de procesos parecidos", "cuantos procesos hay en el mismo tipo y periodo",
    ),
    "history": (
        "esta empresa ya habia ganado algo de esta entidad", "tienen historial juntos el comprador y el proveedor",
        "antes de este contrato ya habian trabajado juntos", "cuantas adjudicaciones previas hay entre ambos", "es la primera adjudicacion de la entidad a esta compania",
        "esa firma es proveedora habitual de esta institucion", "han repetido la relacion comercial estas dos partes",
        "contratos anteriores de la entidad con el ganador", "cuantos procesos ha ganado la empresa con este mismo comprador",
        "la entidad le ha vuelto a adjudicar a la misma empresa", "alguna vez le habian dado contrato antes a este proveedor",
    ),
    "registry_sri": (
        "que actividad economica registra la empresa ganadora en el sri", "como esta el ruc del ganador, activo o suspendido",
        "desde cuando esta inscrito el proveedor en el servicio de rentas", "cual es la actividad principal registrada del adjudicado",
        "en que fecha empezo a operar el ganador segun el sri", "el contribuyente ganador esta activo",
        "dime el estado tributario del proveedor", "que dice el sri sobre la empresa adjudicada", "inicio de actividades de la empresa, segun el registro tributario",
        "en que actividad esta registrado el proveedor", "tiene ruc vigente la empresa que gano",
    ),
    "registry_company": (
        "que clase de compañia es el proveedor adjudicado", "es sociedad anonima o limitada la ganadora", "cual es el tipo societario del adjudicatario",
        "la empresa ganadora figura en la superintendencia de companias, que tipo es", "como esta registrada legalmente la empresa que gano",
        "forma juridica de la compañia ganadora", "es una empresa unipersonal, anonima o de otro tipo", "que tipo de sociedad es el que se llevo el contrato",
        "tipo de persona juridica del ganador", "que figura societaria tiene el adjudicado", "en que categoria de compania esta el ganador",
    ),
    "ghost": (
        "el ganador consta en el listado de empresas inexistentes del sri", "esta empresa aparece como fantasma en el catastro tributario",
        "la ganadora esta en la lista de contribuyentes no ubicados o fantasmas", "figura el adjudicado entre las empresas fantasma",
        "el sri marco al proveedor como empresa fantasma", "revisaron si el ganador esta en el registro de empresas fantasmas",
        "es el proveedor una de las companias fantasma del listado oficial", "consta en el catastro de fantasmas la empresa adjudicada",
        "hay alguna marca de empresa fantasma sobre el ganador", "el ruc del adjudicado esta en la nomina de empresas ficticias del sri",
    ),
    "enquiries_count": (
        "cuantas preguntas se hicieron en la fase de aclaraciones", "hubo preguntas de los oferentes, cuantas",
        "numero de consultas realizadas por los participantes", "cuantas inquietudes se registraron en el proceso",
        "se respondieron preguntas, y cuantas fueron", "cuantas preguntas y respuestas hubo", "cantidad de preguntas formuladas durante la convocatoria",
        "el proceso tuvo etapa de preguntas, cuantas se plantearon", "cuantas consultas respondio la entidad", "cuantas dudas se plantearon en el portal",
    ),
    "enquiries_timing": (
        "cuantos dias demoro la entidad en contestar las preguntas", "que tan rapido respondieron las consultas de los oferentes",
        "tiempo que tomo responder las aclaraciones", "en cuanto tiempo se dieron las respuestas a las preguntas",
        "demora promedio de la entidad para responder consultas", "cuanto se tardaron en responder a los proveedores",
        "cual fue el plazo de respuesta a las preguntas de los oferentes", "las preguntas se contestaron a tiempo o con retraso",
        "cuantos dias paso entre pregunta y respuesta", "la entidad respondio rapido las consultas",
    ),
    "enquiries_late": (
        "hubo preguntas casi al final del periodo de consultas", "se recibieron preguntas en los ultimos dias antes del cierre de ofertas",
        "llegaron consultas muy cerca de la fecha limite", "alguna pregunta se hizo ya sobre la hora de cierre",
        "cuantas preguntas llegaron a ultimo momento", "las consultas se concentraron al final del plazo",
        "se preguntó algo en los dias previos al cierre", "hubo preguntas tardias de los oferentes",
        "preguntas enviadas pegadito al cierre", "alguien hizo consultas pocos dias antes de terminar la recepcion de ofertas",
    ),
    "company_incorporation": (
        "en que fecha fue constituida la empresa adjudicada", "que edad tiene la compania ganadora", "hace cuantos años existe el proveedor",
        "cuando se creo la sociedad que gano", "fecha de creacion de la empresa ganadora", "que antiguedad tiene la firma adjudicada",
        "la empresa ganadora es nueva o ya tiene años", "en que año se constituyo el proveedor", "cuanto tiempo llevaba constituida cuando gano",
        "la compañia se fundo antes o despues de abrirse el proceso", "cuando nacio legalmente el proveedor",
    ),
    "company_capital": (
        "cual es el capital social de la empresa ganadora", "cuanto es el capital pagado del proveedor", "de cuanto es el capital suscrito de la compañia",
        "con que capital cuenta la firma adjudicada", "capital de la empresa en dolares", "que tan grande es el capital de la sociedad ganadora",
        "monto del capital social del adjudicatario", "cuanto tiene registrado como capital el proveedor", "la empresa tiene capital suficiente para este contrato",
        "capital declarado por la ganadora ante la superintendencia", "capital suscrito del contratista",
    ),
    "pair_others": (
        "que otros procesos ha ganado este proveedor con esta entidad", "cuanto dinero mas ha recibido la empresa de este comprador",
        "total acumulado que la entidad le ha adjudicado al proveedor", "otros contratos de esta empresa con la misma institucion",
        "cuanto suma todo lo que le han adjudicado a esta firma en esta entidad", "ademas de este proceso, cuanto le han adjudicado",
        "monto acumulado de adjudicaciones entre comprador y proveedor", "que mas le ha comprado la entidad a esta compania",
        "los demas contratos entre ellos, de cuanto son", "adjudicaciones adicionales del mismo comprador a la misma empresa en otros procesos",
        "valor de los otros procesos que le dieron al ganador en esta misma entidad",
    ),
}

HELDOUT2_SIGNAL_PHRASINGS: tuple[str, ...] = (
    "explicame la alerta {label}", "como se interpreta {label} en este proceso", "no se que es eso de {label}, me ayudas",
    "de donde sale la marca {label}", "que tiene que ver {label} con esta compra", "{label}, que significa exactamente",
    "me puedes aclarar la senal llamada {label}", "por favor detalla la bandera {label}", "cual es el criterio detras de {label}",
    "quisiera entender que mide {label}", "por que se activo {label} para este proceso", "que datos respaldan la señal {label}",
)

HELDOUT2_ALL_SIGNALS_PHRASINGS: tuple[str, ...] = (
    "dame la lista de alertas de este proceso", "cuales son las banderas rojas que salieron", "que señales se activaron en esta compra",
    "muestrame todas las alertas disparadas", "cuantas senales de riesgo hay y cuales son", "este proceso prendio alguna alarma, cual",
    "resumen de los indicadores de riesgo del proceso", "que alertas detecto el sistema aqui", "enumera los red flags de esta contratacion",
    "hay indicadores marcados en este proceso", "what risk signals does this process have", "cuales son los focos rojos segun los datos",
)

HELDOUT2_ABSENT_INVESTIGATION: tuple[str, ...] = (
    "cuantos empleados tiene la empresa ganadora en nomina", "se hizo una consulta en vivo al sri sobre el proveedor ahora mismo",
    "en que momento llegaron las consultas de los oferentes", "ha sido auditada la entidad por la contraloria", "cuantos trabajadores afiliados al iess tiene la compañia",
    "cuales son los balances financieros de la empresa adjudicada", "hay juicios o demandas contra la empresa ganadora",
    "cuando fue la ultima inspeccion al local de la empresa", "que examenes especiales ha tenido esta institucion",
    "la empresa tiene deudas pendientes con el sri, consulta actual", "el proveedor ha sido multado antes por la superintendencia",
    "cuantas sucursales tiene el proveedor",
)

HELDOUT2_NOT_IN_THE_DATA: tuple[str, ...] = (
    "cuanto dura la garantia tecnica del equipo", "en cuantos dias calendario se debe entregar", "que marca y modelo se pidio",
    "cual es la forma de pago, anticipo o contra entrega", "como se llama el contrato, que numero tiene", "que penalidades se aplican por retraso",
    "quien es el fiscalizador de la obra", "cuales son las especificaciones tecnicas del bien", "donde exactamente se ejecuta el trabajo",
    "que porcentaje de anticipo se entrego", "cuales eran los requisitos habilitantes del pliego", "cuantas visitas tecnicas se hicieron",
    "el contrato fue liquidado ya", "se firmo alguna adenda al contrato", "hay seguro o poliza de cumplimiento, de cuanto",
    "quien es el administrador designado del contrato", "que plazo de ejecucion tiene la obra", "cual fue el puntaje que obtuvo cada oferta",
    "cual es la vigencia del contrato", "que garantia de fiel cumplimiento pidieron", "cuantas unidades se compraron exactamente",
    "en que fecha se recibio el bien a satisfaccion", "que clausulas de terminacion tiene el contrato", "que reajuste de precios se acordo",
)

HELDOUT2_OFF_TOPIC: tuple[str, ...] = (
    # share exactly one ambiguous word
    "cual es la capital de Australia", "cuanto cuesta una pizza familiar", "quien ganó el mundial de 1986", "que hora es en el plazo horario de Tokio",
    "cual es el objeto directo de esta oracion", "precio del dolar hoy", "cuantos participantes tuvo el Mundial de Rusia", "entidad bancaria mas grande del mundo",
    "cual es la fecha de nacimiento de Einstein", "señal de transito de pare, que significa", "proveedor de internet mas rapido de Quito",
    "contrato de arriendo de mi casa como se redacta", "licitacion de un reality show, cuando sale", "cual es el costo de vida en Madrid",
    "que valor tiene el pi redondeado", "oferta de vuelos a Miami en diciembre", "que oferente de celulares tiene mejor camara",
    "cual es la institucion educativa mas antigua de America", "que significa la palabra contrato en latin", "en que fecha cae la Semana Santa",
    "quien es el ganador del Oscar a mejor pelicula este año", "que señal de wifi es mejor, 2.4 o 5 GHz", "cual es el riesgo de comer pollo crudo",
    "comparar iPhone con Samsung, cual conviene", "que habia antes del Big Bang", "como se fundo una empresa de videojuegos famosa",
    "cual es el mejor equipo para jugar en la sociedad de ajedrez", "que activo digital sube mas, bitcoin o ether", "balance de un auto, como se hace",
    "tengo una consulta sobre mi tarea de matematicas", "cual es el tema de la pelicula Titanic", "en que hospital nacio Messi",
    "como hacer una obra de teatro en el colegio", "que servicio de streaming tiene mas series", "cual es el metodo mas rapido para aprender ingles",
    "cual es el estado del clima en Cuenca", "catalogo de recetas de postres ecuatorianos", "procedimiento para hacer arroz con pollo",
    "cual es el plazo para que madure un aguacate", "cuanto vale un boleto al estadio Atahualpa", "precio de la gasolina super en Estados Unidos",
    "cual es el mejor proveedor de harina para hacer pan casero", "que objeto cayo del cielo en la pelicula de Kubrick",
    "cual es la entidad que organiza la Copa Libertadores", "que fecha es el dia de la madre en Mexico", "cual es la capital de Mongolia",
    "cuando termina el contrato de Neymar con el club", "quien gano el premio Nobel de literatura en 1982", "cual es el costo de un pasaje en el metro de Nueva York",
    "oferta de gimnasio en mi barrio, que me recomiendas", "senal de humo en la pelicula de indios, que significaba", "riesgo de que llueva manana en Guayaquil",
    "cual es el valor del numero e", "que institucion creo el internet", "como se llama el ganador de la liga de España", "antes de cocinar el arroz, hay que lavarlo",
    "cuantos jugadores tiene un equipo de futbol", "empresa mas grande de tecnologia del mundo", "que hospital veterinario me queda cerca de casa",
    "sociedad protectora de animales de Loja, telefono",
    # completely unrelated
    "cuentame un cuento corto para dormir", "como se dice gracias en japones", "cuantos huesos tiene el cuerpo humano", "que planeta es el mas grande",
    "recomiendame una cancion para bailar", "como puedo bajar de peso rapido", "cuantos litros son tres galones", "cual es el rio mas largo de Sudamerica",
    "como se hace un pastel de chocolate", "quien pinto la Mona Lisa", "como cambio la llanta de mi carro", "cuanto es la raiz cuadrada de 144",
)

HELDOUT2_COMPARISON: tuple[str, ...] = (
    "esto es normal o es raro comparado con otros", "como esta frente a compras parecidas", "en que posicion queda respecto a procesos similares",
    "se sale de lo comun frente a otros del mismo tipo", "como se compara este proceso con los demas de su clase", "este caso esta dentro de lo tipico entre procesos parecidos",
    "ponlo al lado de procesos similares, que diferencias hay en numeros", "como queda parado frente al resto de contrataciones iguales",
    "en relacion a compras equivalentes, esta por encima o por debajo", "este proceso se parece al promedio de los similares",
    "contrastalo con otros procesos del mismo tipo y dime donde cae", "como le fue frente a sus pares en participantes y precio adjudicado",
    "frente a otros concursos de este estilo, esta en la media", "cual es su ubicacion respecto de procesos comparables",
    "el numero de oferentes de este esta alineado con el de otros similares", "dime como se ve este proceso contra su grupo de referencia",
    "versus procesos del mismo tipo, el valor adjudicado es habitual", "kmo esta este proceso comparado con otros semejantes",
)

HELDOUT2_COMPOUND: tuple[tuple[str, str, str], ...] = (
    ("quien gano y por cuanto dinero se adjudico", "winner", "amounts"),
    ("de que se trata el proceso y cuantas empresas ofertaron", "object", "tenderers"),
    ("que entidad lo convoco y que tipo de procedimiento fue", "entity", "procedure"),
    ("cuando se adjudico y a quien", "award_dates", "winner"),
    ("dime el cpc, y tambien que se compro", "cpc", "object"),
    ("a que se dedica la empresa ganadora y que tipo de compañia es", "registry_sri", "registry_company"),
    ("la entidad ya le habia adjudicado antes al ganador y cuantos oferentes habia normalmente", "history", "context_tenderers"),
    ("cuanto fue el presupuesto, ademas quien se lo llevo", "amounts", "winner"),
    ("cuantos postularon y en que fecha se adjudico", "tenderers", "award_dates"),
    ("que institucion compro y cual es el codigo cpc", "entity", "cpc"),
    ("el proveedor esta activo en el sri, e hizo negocios antes con la entidad", "registry_sri", "history"),
    ("que procedimiento se uso y que se contrato", "procedure", "object"),
    ("cuantos competidores hubo, y cuantos suele haber en procesos parecidos", "tenderers", "context_tenderers"),
    ("quien es el adjudicado y que forma societaria tiene", "winner", "registry_company"),
    ("monto adjudicado y fecha de adjudicacion", "amounts", "award_dates"),
    ("que organismo es el comprador, y quien le vendio", "entity", "winner"),
    ("cual es el objeto de la compra y el monto", "object", "amounts"),
    ("cuantos le entraron y quien gano", "tenderers", "winner"),
    ("tambien quisiera saber el estado del proceso, ademas de cual es la entidad", "procedure", "entity"),
    ("el ganador tiene ruc vigente y de que tipo de empresa se trata", "registry_sri", "registry_company"),
    ("cuanto costo y cuando se firmo", "amounts", "award_dates"),
    ("cual es el cpc y que tipo de proceso es", "cpc", "procedure"),
    ("han trabajado juntos antes la entidad y el ganador, y como se llama ese ganador", "history", "winner"),
    ("que se contrato, ademas cuantos oferentes tiene en tipico este tipo de proceso", "object", "context_tenderers"),
    ("quien compro y cuantos participaron", "entity", "tenderers"),
    ("en que fecha se adjudico y bajo que procedimiento", "award_dates", "procedure"),
    ("cual fue el ganador y desde cuando opera segun el sri", "winner", "registry_sri"),
    ("cuantas empresas ofertaron, y el valor", "tenderers", "amounts"),
    ("dime el objeto y el cpc de lo que se compro tambien", "object", "cpc"),
    ("quien gano e historial con la entidad", "winner", "history"),
)
