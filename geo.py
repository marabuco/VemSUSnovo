"""Georreferenciamento: validação das coordenadas oficiais + geocodificação de reserva (Nominatim/OSM)."""
import asyncio
import re
import time

import httpx

from .config import Settings


def parse_coord(value) -> float | None:
    """Aceita número, '-8,0476', ' -8.0476 '. Rejeita vazio e 0 (valor típico de 'sem dado')."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        num = float(value)
    else:
        txt = str(value).strip().replace(",", ".")
        if not re.fullmatch(r"[-+]?\d+(\.\d+)?", txt):
            return None
        num = float(txt)
    return None if num == 0 else num


def _inside(settings: Settings, lat: float, lng: float) -> bool:
    return (
        settings.geo_min_lat <= lat <= settings.geo_max_lat
        and settings.geo_min_lng <= lng <= settings.geo_max_lng
    )


def validate_coords(settings: Settings, lat_raw, lng_raw) -> tuple[float, float] | None:
    """Devolve (lat, lng) válidos para o Recife, corrigindo erros comuns de cadastro:
    sinal perdido e latitude/longitude invertidas. Se nada serve, devolve None."""
    lat, lng = parse_coord(lat_raw), parse_coord(lng_raw)
    if lat is None or lng is None:
        return None
    candidates = [
        (lat, lng),
        (-abs(lat), -abs(lng)),  # sinal perdido
        (lng, lat),  # invertidas
        (-abs(lng), -abs(lat)),
    ]
    for c_lat, c_lng in candidates:
        if _inside(settings, c_lat, c_lng):
            return round(c_lat, 6), round(c_lng, 6)
    return None


class Geocoder:
    """Nominatim (OpenStreetMap) com cache, 1 req/s e limite por sincronização.
    Só é usado para unidades SEM coordenada válida na base oficial."""

    def __init__(self, settings: Settings, db, transport: httpx.AsyncBaseTransport | None = None):
        self.s, self.db, self.transport = settings, db, transport
        self.calls = 0
        self._last = 0.0

    async def geocode(self, address: str, neighborhood: str) -> tuple[float, float] | None:
        if not self.s.geocode_enabled or not address.strip():
            return None
        key = f"{address}|{neighborhood}".lower()
        cached = self.db.geocode_cache_get(key, self.s.geocode_retry_days)
        if cached is not None:
            return cached or None  # () = falha já conhecida
        if self.calls >= self.s.geocode_max_per_sync:
            return None
        self.calls += 1
        wait = 1.1 - (time.monotonic() - self._last)
        if wait > 0:
            await asyncio.sleep(wait)
        self._last = time.monotonic()
        params = {
            "q": f"{address}, {neighborhood}, Recife, PE, Brasil".replace(" ,", ","),
            "format": "jsonv2",
            "limit": 1,
            "countrycodes": "br",
            "viewbox": f"{self.s.geo_min_lng},{self.s.geo_max_lat},{self.s.geo_max_lng},{self.s.geo_min_lat}",
            "bounded": 1,
        }
        try:
            async with httpx.AsyncClient(
                timeout=15, transport=self.transport, headers={"User-Agent": self.s.nominatim_user_agent}
            ) as client:
                resp = await client.get(self.s.nominatim_url, params=params)
                resp.raise_for_status()
                hits = resp.json()
        except (httpx.HTTPError, ValueError):
            return None  # erro transitório: não grava cache negativo
        found = validate_coords(self.s, hits[0].get("lat"), hits[0].get("lon")) if hits else None
        self.db.geocode_cache_put(key, found)
        return found
