"""FastAPI application factory (`veedor.api.main:app`)."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from veedor.api.errors import register_error_handlers
from veedor.api.http_cache import HttpCacheMiddleware
from veedor.api.meta import VERSION
from veedor.api.security import BodySizeLimitMiddleware, ReadRateLimitMiddleware, SecurityHeadersMiddleware
from veedor.api.v1 import router as v1_router
from veedor.api.v1.investigations import router as investigations_router
from veedor.api.v1.similar import router as similar_router
from veedor.api.warmup import warm_caches_on_start
from veedor.core.settings import get_settings
from veedor.infrastructure.telemetry import instrument_app, setup_telemetry

logger = logging.getLogger(__name__)

DESCRIPTION = """
Radar abierto de riesgo en la contratación pública del Ecuador.

La API expone **señales de riesgo** (indicadores transparentes calculados sobre datos abiertos de
SERCOP y registros públicos), un puntaje por proceso y expedientes de evidencia. Reporta
indicadores, **nunca acusaciones**. Las personas naturales no se nombran: su nombre se muestra
como "Persona natural" y su RUC conserva solo los primeros cuatro dígitos.

Todos los errores usan el formato `{"error": {"code", "message"}}`.
"""

TAGS = [
    {"name": "resumen", "description": "Totales, cobertura y distribución de puntajes."},
    {"name": "procesos", "description": "Procesos de contratación, señales y expedientes."},
    {"name": "proveedores", "description": "Perfiles de proveedores y registros públicos."},
    {"name": "entidades", "description": "Entidades contratantes."},
    {"name": "señales", "description": "Catálogo de indicadores."},
    {"name": "glosario", "description": "Términos de la contratación pública, en español claro."},
    {"name": "revisiones", "description": "Revisión humana de procesos (PostgreSQL)."},
    {"name": "health", "description": "Estado del servicio."},
]


SWAGGER_VERSION = "5.17.14"
SWAGGER_BASE = f"https://cdn.jsdelivr.net/npm/swagger-ui-dist@{SWAGGER_VERSION}"
# Subresource Integrity of the pinned assets (sha384).
SWAGGER_JS_SRI = "sha384-wmyclcVGX/WhUkdkATwhaK1X1JtiNrr2EoYJ+diV3vj4v6OC5yCeSu+yW13SYJep"
SWAGGER_CSS_SRI = "sha384-wxLW6kwyHktdDGr6Pv1zgm/VGJh99lfUbzSn6HNHBENZlCN7W602k9VkGdxuFvPn"

DOCS_HTML = f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><title>Veedor API</title>
<link rel="stylesheet" href="{SWAGGER_BASE}/swagger-ui.css"
 integrity="{SWAGGER_CSS_SRI}" crossorigin="anonymous">
</head><body><div id="swagger-ui"></div>
<script src="{SWAGGER_BASE}/swagger-ui-bundle.js"
 integrity="{SWAGGER_JS_SRI}" crossorigin="anonymous"></script>
<script>SwaggerUIBundle({{url: "/openapi.json", dom_id: "#swagger-ui"}});</script>
</body></html>"""


def create_app(*, warm_up: bool = False) -> FastAPI:
    docs_enabled = get_settings().docs_enabled
    app = FastAPI(
        title="Veedor API",
        version=VERSION,
        description=DESCRIPTION,
        openapi_tags=TAGS,
        docs_url=None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs_enabled else None,
        redirect_slashes=False,  # a redirect would build its Location from the Host header
        lifespan=warm_caches_on_start if warm_up else None,
    )
    if docs_enabled:
        app.add_api_route("/docs", lambda: HTMLResponse(DOCS_HTML), include_in_schema=False)
    app.add_middleware(HttpCacheMiddleware)  # innermost: CORS and the security headers wrap its output
    settings = get_settings()
    if settings.read_rate_per_minute == 0 or settings.read_search_rate_per_minute == 0:
        logger.warning(
            "read rate limit is OFF (general=%s/min, search=%s/min; 0 = off). Fine for local development; "
            "a public deployment sets VEEDOR_READ_RATE_PER_MINUTE and VEEDOR_READ_SEARCH_RATE_PER_MINUTE.",
            settings.read_rate_per_minute,
            settings.read_search_rate_per_minute,
        )
    app.add_middleware(  # inside CORS and the security headers, so a 429 carries both
        ReadRateLimitMiddleware,
        per_minute=settings.read_rate_per_minute,
        search_per_minute=settings.read_search_rate_per_minute,
        exempt=settings.read_rate_exempt,
        max_keys=settings.read_rate_max_keys,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origins,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["Retry-After"],  # a browser may read how long to wait after a 429
    )
    app.add_middleware(BodySizeLimitMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    setup_telemetry(get_settings().otel_service_name)  # no-op without VEEDOR_OTEL_ENDPOINT
    instrument_app(app)  # outermost: request span and RED metrics by route template
    register_error_handlers(app)
    app.include_router(v1_router, prefix="/api/v1")
    app.include_router(investigations_router, prefix="/api/v1")
    app.include_router(similar_router, prefix="/api/v1")
    return app


app = create_app(warm_up=True)
