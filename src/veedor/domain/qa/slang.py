# ruff: noqa: E501
"""Wording the screen refuses beyond the project's own accusation vocabulary (pure data, folded text).

`domain.dossier.vocabulary.FORBIDDEN_PATTERN` and `domain.quotes.allegation` already refuse the formal words
(corrupción, fraude, soborno, sobreprecio, direccionado, colusión...). People do not ask that way: they use Ecuadorian
and Latin American slang, euphemisms, misspellings and English. This module lists that vocabulary. Everything is
matched on `screen._fold` text (lower case, accents and ñ folded, punctuation turned into spaces).

Words that can also be a neutral data question were decided one by one, by what a visitor means:

* `sobreprecio`, `direccionado`, `amañado`, `arreglado`, `a dedo`, `negociado`: accusations in every use found; they
  presuppose a verdict the data cannot give (the project's vocabulary already treats the first two so). A visitor who
  wants the numbers asks "cuánto se adjudicó" or "cuánto pasó del presupuesto" (`sobrecosto`, `diferencia`,
  `excedió` are neutral and are answered).
* `dirigido`: an accusation only when it says the process was steered ("dirigido a una sola empresa", "a favor de",
  "el proceso estaba dirigido"); "dirigido a bienes, obras o servicios" asks for the audience of the process.
* `lavado` only as "lavado de dinero/activos/plata"; `palanca`, `amarre`, `argolla`, `rosca`: slang for a clique or a
  favour (no neutral meaning in a question about a public purchase).
* `raro`, `normal`, `extraño`, `atípico`, `inusual`: a verdict when asked about the process itself ("¿es raro?"), but
  a position question when it compares the process with similar ones ("¿es normal o raro comparado con otros?").
  That one is not a judgement and returns the comparison facts. A request to compare that also asks for a verdict
  through another word ("¿es sospechoso comparado con otros?") stays a judgement.
"""

from __future__ import annotations

import re

_SLANG = re.compile(
    r"\b(?:coima\w*|soborn\w*|mordida\w*|tajada\w*|diezm\w*|cohech\w*|"
    r"bajo (?:la )?mesa|por debajo (?:de la mesa|del agua|de cuerda)|"
    r"(?:plata|dinero|billete\w*|platita) (?:negr[oa]s?|suci[oa]s?)|"
    r"se (?:la |lo |les |le )?(?:embols\w*|llevar\w* (?:la |su |el )?(?:plata|torta|tajada|billete|diezmo|comision|parte|pastel|todo)|"
    r"repartier\w*|reparti\w* (?:la )?(?:torta|pastel|plata))|repartij\w*|cuoteo|pagar favores|favores politic\w*|"
    r"chanchull\w*|tong[oa]s?|amarre\w*|amarrad\w*|amarrar\w*|palanque\w*|(?:tiene|tienen|con|por|mediante|usaron|usar|uso de|tener) (?:la |una |las )?palancas?|compadraz\w*|compadres?|argolla\w*|camarilla\w*|"
    r"contubernio\w*|trinca\w*|manos? negras?|mafia\w*|conchaba\w*|confabula\w*|colud\w*|colusi\w*|"
    r"negociados?|enchufad\w*|pituto\w*|tapadera\w*|encubr\w*|gato encerrado|influencias?|"
    r"pact(?:o|os|aron|ado|ados) (?:entre|previo|secreto)|arreglad[oa]s?|arreglaron|"
    r"(?<!metros )(?<!metro )(?<!pies )cuadrad[oa]s?(?! de| en)|cuadraron|trucad[oa]s?|manipulad[oa]s?|tramad[oa]s?|"
    r"torcid[oa]s?|chuec[oa]s?|turbi[oa]s?|podrid[oa]s?|suci[oa]s?|manejo (?:oscuro|turbio|sucio)|"
    r"amiguism\w*|dedazo\w*|a dedo|a la medida|entre (?:amigos|panas|familiares|compadres|conocidos|parientes)|"
    r"testaferr\w*|prestanombres?|empresas? (?:de papel|pantalla)|lavado de (?:plata|dinero|activos|capitales)|"
    r"lavar (?:plata|dinero|capitales|activos)|ladron\w*|ratero\w*|bandid\w*|sinverguenz\w*|estaf\w*|pillos?|"
    r"se quedaron con (?:la |el |su )?(?:plata|dinero|torta|billete)|desfalc\w*|malvers\w*|peculad\w*|evasion fiscal|"
    r"desvi(?:o|aron|ar) (?:de )?(?:fondos|plata|dinero)|prevaric\w*|extors\w*|chantaj\w*|se robaron|robaron|"
    r"(?:es|fue|esta|estaba|estuvo|sido) (?:todo )?(?:un )?(?:robo|choreo|timo|engano|trampa|farsa|show|circo)|"
    r"(?:huele|olor|apesta|hiede) (?:a|mal)|algo (?:raro|extrano|oscuro|turbio|sucio|malo)|mal(?:a)? fe|doble moral|nada limpio)\b"
)

_ENGLISH = re.compile(
    r"\b(?:rigged|rigging|rig|brib\w*|kickbacks?|payoffs?|graft|corrupt\w*|fraud\w*|scams?|shady|crooked|fishy|sketchy|dodgy|"
    r"suspicious|illegal\w*|illicit|guilty|collu\w*|launder\w*|embezzl\w*|nepotis\w*|cronyis\w*|under the table|backroom|"
    r"wrongdoing|misconduct|cheat\w*|stole\w*|steal\w*|theft|thiev\w*|swindl\w*|good or bad|right or wrong|legit|lawful|"
    r"cooked|fixed (?:bid|bids|contract|tender|process|auction)|pre ?arranged)\b"
)

_OPINION = re.compile(
    r"\b(?:(?:que|tu|su) (?:opinas|piensas|crees|opina|piensa|cree|consideras)|(?:tu|su) (?:opinion|parecer|criterio|veredicto|conclusion|juicio|valoracion)|"
    r"(?:lo |la )?(?:recomiendas|recomienda|aconsejas)|(?:te|le) parece (?:bien|mal|correct\w*|just\w*|limpi\w*|normal|raro|sospechos\w*|buen\w*|mal\w*|legal|transparente|honest\w*)|"
    r"(?:dame|da|emite|dime) (?:tu |un |una )?(?:opinion|veredicto|juicio|conclusion|valoracion|diagnostico)|"
    r"(?:esta|estan|sera|seria) (?:bien|mal)\b(?! (?:cerrad|publicad|escrit))|(?:bien o mal|mal o bien|bueno o malo|buena o mala|limpio o sucio|legal o ilegal|honesto o deshonesto|justo o injusto)|"
    r"(?:es|fue|esta|sera|seria) (?:una |un )?(?:buena|mala|buen|mal) (?:compra|contrato|proceso|licitacion|adjudicacion|decision|negocio|oferta)|"
    r"(?:contrato|compra|proceso|licitacion|adjudicacion|decision|negocio) (?:correct[oa]|incorrect[oa]|justo|injusto|limpio|bueno|malo)|"
    r"(?:debo|debemos|deberia|deberiamos) (?:preocupar\w*|desconfiar|confiar|alarmar\w*|dudar)|"
    r"(?:se )?(?:hizo|hicieron|actuo|actuaron|obro|obraron|manejo|manejaron) (?:bien|mal|correcta\w*|incorrecta\w*|honest\w*|deshonest\w*|con transparencia|sin transparencia)|"
    r"(?:es|esta|fue|son|sera) (?:justo|injusto|justa|injusta|aceptable|inaceptable|etico|etica|antietico|inmoral|moral|decente|vergonzos\w*|escandalos\w*|grave|preocupante|alarmante|incorrect\w*|correct\w*|erroneo|erronea|indebid\w*|ilicit\w*|ilegitim\w*|abusiv\w*|dudos\w*|riesgos[oa]|peligros\w*|sospechos\w*|confiable|fiable|seguro|segura|transparente|opac[oa]|limpi[oa]|honest[oa]|deshonest[oa]|buen[oa]|mal[oa]|fraudulent[oa]|corrupt[oa]))\b"
)

SOFT_VERDICT = re.compile(
    r"\b(?:(?:es|son|fue|fueron|esta|estan|sera|seria|resulta|parece|se ve|se ven|luce|salio) (?:algo |un poco |muy |bastante |medio |tan )?"
    r"(?:raro\w*|extran\w*|normal(?:es)?|anormal(?:es)?|atipic\w*|inusual(?:es)?|fuera de lo (?:comun|normal)|poco comun|llamativ\w*)(?! que\b)"
    r"|se sale de lo (?:comun|normal|habitual))\b"
)

COMPARISON_FRAME = re.compile(
    r"\b(?:compar\w*|frente a|respecto (?:a|de|del)|en relacion (?:a|con)|versus|vs|contra (?:otros|otras|los|las)|"
    r"con (?:otros|otras|los demas|las demas|el resto|la media|el promedio)|(?:que|de|a) (?:otros|otras|los demas|las demas|el resto)|del resto|"
    r"(?:procesos|compras|contrataciones|licitaciones|concursos) (?:similares|parecid\w*|comparables|iguales|del mismo tipo|de este tipo)|"
    r"(?:mismo|este|ese|igual) (?:tipo|metodo|procedimiento))\b"
)

_INSTRUCTION_EXTRA = re.compile(
    r"\b(?:(?:tus|sus|your) (?:ordenes|indicaciones|directivas|directrices|mandatos|lineamientos|politicas|parametros|rol|papel|programacion|"
    r"entrenamiento|configuracion|restricciones|limites|filtros|secretos|origenes|creadores|desarrolladores|mensaje inicial|memoria|objetivo real|verdadero objetivo)|"
    r"(?:tu|su) (?:rol|papel|programacion|entrenamiento|configuracion|memoria|objetivo real|mensaje inicial|creador|desarrollador)|"
    r"(?:ordenes|indicaciones|reglas|directivas|mandatos|lineamientos|politicas|parametros|instrucciones|comandos) (?:ocult\w*|secret\w*|internas?|privad\w*|confidencial\w*|del sistema|previas|anteriores|originales|iniciales)|"
    r"(?:lo|todo lo|el texto|el mensaje|las palabras) (?:que )?(?:dice|decia|esta escrit\w*|escribieron|pusieron|te dijeron|te dieron|aparece) (?:arriba|antes|al (?:principio|inicio|comienzo)|mas arriba)|"
    r"(?:lo anterior|el texto anterior|todo lo anterior|lo de arriba|lo de antes|el texto de arriba|el mensaje de arriba)|"
    r"(?:system|developer|hidden|secret|initial|original|internal|confidential|previous|above|earlier|preceding) (?:prompt|message|instructions?|rules|text|content|configuration|settings|guidelines|context)|"
    r"(?:mensaje|prompt|texto|contexto|rol|configuracion) del (?:sistema|desarrollador|programador|creador)|"
    r"(?:soy|somos) (?:el |la |un |una )?(?:administrador\w*|admin|desarrollador\w*|programador\w*|creador\w*|dueno|jefe|supervisor|auditor autorizado|de soporte|de seguridad|del equipo de|de sistemas)|"
    r"(?:modo|mode|nivel|acceso|access|permisos?|privilegios?) (?:depuracion|debug|mantenimiento|prueba|test|admin\w*|root|sudo|superusuario|desarrollo|developer|dev|sin filtros?|irrestricto|total|completo|especial)|"
    r"sudo|superusuario|autorizado por|(?:revela\w*|reveal|muestrame|mostrar|imprime\w*|imprimir|copia\w*|filtra\w*|dump|leak|expose|disclose|print|show me|repite\w*|repetir|repeat|recita\w*|dicta\w*|cuentame|dime|decime) (?:me )?(?:todo|toda|tus|tu|sus|su|your|the) (?:propi\w* )?(?:ordenes|reglas|indicaciones|configuracion|contexto|memoria|entrenamiento|programacion|prompt|mensaje|texto|instrucc\w*|rol|directivas|restricciones|secretos|datos internos|informacion interna|que sabes|que te dijeron)|"
    r"(?:empieza|comienza|inicia|termina|finaliza|acaba|start|begin|end|finish) (?:tu |la |su |your |the )?(?:respuesta|answer|reply|response|contestacion) (?:con|diciendo|by|with)|"
    r"(?:nueva|new) (?:tarea|task|mision|mission|orden|order|consigna|rol|role|personalidad|persona|identidad|instruccion|instruction|regla|rule)|"
    r"(?:olvida\w*|ignora\w*|descarta\w*|deja de lado|desactiva\w*|anula\w*|saltate|omite\w*|quita\w*|elimina\w*|borra\w*|suspende\w*|levanta\w*|rompe\w*|evita\w*|burla\w*|sobrescribe\w*|reemplaza\w*) (?:\w+ ){0,3}(?:reglas|filtros|restricciones|limites|protecciones|seguridad|controles|salvaguardas|censura|barreras|candados|pautas|normas|guardrails|safeguards|rules|filters|restrictions|limits|safety)|"
    r"(?:you are now|you re now|act as|acts as|pretend|imagina|suponte|supongamos|finge|simula|hazte pasar|hacerte pasar|comportate como|juega a|en el rol de|en el papel de|interpreta\w*|encarna\w*|roleplay|role play)|"
    r"(?:traduce|translate|codifica|encode|decodifica|decode|cifra|encrypt|transcribe|resume|summarize|summarise|parafrasea|paraphrase|explica|explain) (?:\w+ ){0,4}(?:tus|tu|sus|su|your|the) (?:reglas|ordenes|instrucc\w*|configuracion|prompt|directivas|restricciones|programacion|indicaciones|rol|rules|instructions|configuration|guidelines|restrictions)|"
    r"(?:en|in|a) (?:base ?64|hexadecimal|hex|binario|morse|rot13|json|yaml|xml|markdown|html|csv|sql|codigo|code|cifrado|ingles|english|frances|french|aleman|german|latin|mayusculas|uppercase|verso|rima|emojis?)|"
    r"(?:cuales son|que son|cuales eran|explicame|explica|dime cuales son) (?:tus|sus) (?:reglas|ordenes|indicaciones|restricciones|instrucciones|directivas|limites|politicas|pautas|normas|configuraciones)|"
    r"(?:quien|que|how|who|what) (?:te|lo) (?:programo|programaron|configuro|configuraron|entreno|entrenaron|creo|crearon|dio|dieron|mando|mandaron|dijo|dijeron)|(?:como|how) (?:fuiste|eres|were you|are you) (?:programad\w*|configurad\w*|entrenad\w*|creat\w*|built|made|trained|configured|programmed)|"
    r"(?:solo|nomas|just) (?:esta vez|this once|por hoy)|(?:por favor|please|porfa) (?:ignora|olvida|ignore|forget|dime tu|show me your|reveal|muestra tu|revela tu))\b"
)

_NOT_AUDIENCE = (
    r"(?! (?:a|para) (?:bienes|obras|servicios|consultoria|pymes|mipymes|micro|pequen\w*|medianas|"
    r"proveedores (?:nacionales|locales)|todos|cualquier|que|quien|quienes)\b)"
)
_DIRIGIDO = re.compile(
    r"\b(?:(?:proceso|contrato|licitacion|concurso|compra|adjudicacion|oferta|pliego|pliegos|esto|todo) "
    r"(?:(?:esta|estaba|estuvo|fue|era|es|sido|seria) )?(?:ya )?(?:todo )?dirigid[oa]s?\b" + _NOT_AUDIENCE +
    r"|(?:estaba|estuvo|fue|era|sido|seria) (?:ya )?(?:todo )?dirigid[oa]s?\b(?! (?:a|para)\b)"
    r"|dirigid[oa]s? (?:a|hacia|para) (?:una|un|esa|ese|alguna|algun|cierta|cierto|determinad[oa]) (?:sola |unica |misma )?"
    r"(?:empresa|firma|compania|proveedor|oferente|ganador|persona|contratista|favorit\w*)"
    r"|dirigid[oa]s? (?:a favor|de antemano|desde antes|desde el inicio|por (?:alguien|adentro|dentro)))\b"
)


def accusation_slang(folded: str) -> bool:
    """Slang, euphemisms, English, opinion requests and a steered process: wording that asks for a verdict."""
    return bool(
        _SLANG.search(folded) or _ENGLISH.search(folded) or _OPINION.search(folded) or _DIRIGIDO.search(folded)
    )


def hidden_instruction(folded: str) -> bool:
    return bool(_INSTRUCTION_EXTRA.search(folded))


def soft_verdict(folded: str) -> bool:
    return bool(SOFT_VERDICT.search(folded))


def comparison_frame(folded: str) -> bool:
    return bool(COMPARISON_FRAME.search(folded))
