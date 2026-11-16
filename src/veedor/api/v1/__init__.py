"""Version 1 of the HTTP API."""

from fastapi import APIRouter

from veedor.api.v1 import (
    buyers,
    catalogue,
    glossary,
    health,
    meta,
    processes,
    provenance,
    quotes,
    reviews,
    stats,
    suppliers,
)

router = APIRouter()
for module in (
    health,
    meta,
    stats,
    processes,
    quotes,
    provenance,
    reviews,
    suppliers,
    buyers,
    catalogue,
    glossary,
):
    router.include_router(module.router)
