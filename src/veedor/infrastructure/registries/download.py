"""Discover and download registry files from official Ecuadorian government hosts."""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, unquote

import httpx

SRI_DATASETS_PAGE = "https://www.sri.gob.ec/datasets"
SUPERCIAS_BASE = "https://appscvsmovil.supercias.gob.ec/ranking/recursos"
ALLOWED_HOSTS = {"www.sri.gob.ec", "descargas.sri.gob.ec", "appscvsmovil.supercias.gob.ec"}
USER_AGENT = "Mozilla/5.0 (compatible; veedor-open-data/0.1)"
MAX_WORKERS = 3
RETRIES = 4

_RUC_ZIP = re.compile(r'href="(https://descargas\.sri\.gob\.ec/download/datosAbiertos/SRI_RUC_[^"]+\.zip)"')
_GHOST_CSV = re.compile(
    r'href="(https://www\.sri\.gob\.ec/o/sri-portlet-biblioteca-alfresco-internet/descargar/'
    r'[0-9a-f-]+/SRI_Catastro_Empresas_Fantasmas\.csv)"',
    re.IGNORECASE,
)


@dataclass(frozen=True)
class RemoteFile:
    url: str
    name: str


def _filename(url: str) -> str:
    return unquote(url.rsplit("/", 1)[-1])


def parse_sri_page(html: str) -> tuple[list[RemoteFile], RemoteFile | None]:
    """Extract per-province RUC zips and the ghost-company CSV from the SRI datasets page."""
    rucs = sorted({m.group(1) for m in _RUC_ZIP.finditer(html)})
    ghost = _GHOST_CSV.search(html)
    return (
        [RemoteFile(_safe_url(u), _filename(u)) for u in rucs],
        RemoteFile(ghost.group(1), _filename(ghost.group(1))) if ghost else None,
    )


def _safe_url(url: str) -> str:
    head, tail = url.rsplit("/", 1)
    return f"{head}/{quote(unquote(tail))}"


def supercias_files() -> list[RemoteFile]:
    return [RemoteFile(f"{SUPERCIAS_BASE}/{n}", n) for n in ("bi_compania.csv", "bi_ranking.csv")]


def _client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=httpx.Timeout(60, read=300)
    )


def discover_sri(client: httpx.Client | None = None) -> tuple[list[RemoteFile], RemoteFile | None]:
    own = client or _client()
    try:
        response = _with_retries(lambda: _get_ok(own, SRI_DATASETS_PAGE))
        return parse_sri_page(response.text)
    finally:
        if client is None:
            own.close()


def _get_ok(client: httpx.Client, url: str) -> httpx.Response:
    response = client.get(url)
    response.raise_for_status()
    return response


def _with_retries[T](action: Callable[[], T]) -> T:
    for attempt in range(RETRIES):
        try:
            return action()
        except httpx.HTTPError:
            if attempt == RETRIES - 1:
                raise
            time.sleep(2**attempt)
    raise AssertionError("unreachable")


def download_file(client: httpx.Client, remote: RemoteFile, dest_dir: Path) -> tuple[Path, bool]:
    """Download one file. Returns (path, downloaded); skips when a complete copy is present."""
    host = httpx.URL(remote.url).host
    if host not in ALLOWED_HOSTS:
        raise ValueError(f"Refusing to download from non-official host: {host}")
    dest_dir.mkdir(parents=True, exist_ok=True)
    final = dest_dir / remote.name
    expected = _remote_size(client, remote.url)
    if final.exists() and (expected is None or final.stat().st_size == expected):
        return final, False
    part = final.with_suffix(final.suffix + ".part")

    def fetch() -> None:
        with client.stream("GET", remote.url) as response:
            response.raise_for_status()
            with part.open("wb") as handle:
                for chunk in response.iter_bytes(1 << 20):
                    handle.write(chunk)

    _with_retries(fetch)
    if expected is not None and part.stat().st_size != expected:
        raise OSError(f"Size mismatch for {remote.name}: {part.stat().st_size} != {expected}")
    part.replace(final)
    return final, True


def _remote_size(client: httpx.Client, url: str) -> int | None:
    try:
        response = _with_retries(lambda: client.head(url))
    except httpx.HTTPError:
        return None
    value = response.headers.get("content-length")
    return int(value) if response.status_code == 200 and value and value.isdigit() else None


def download_all(
    files: list[RemoteFile], dest_dir: Path, on_done: Callable[[str, bool], None] | None = None
) -> dict[str, bool]:
    """Download with at most MAX_WORKERS concurrent connections. Returns name -> newly downloaded."""
    results: dict[str, bool] = {}
    with _client() as client, ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(download_file, client, f, dest_dir): f for f in files}
        for future, remote in futures.items():
            _, fresh = future.result()
            results[remote.name] = fresh
            if on_done:
                on_done(remote.name, fresh)
    return results
