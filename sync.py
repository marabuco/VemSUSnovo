"""Sincronização: CKAN -> normalização -> geocodificação de reserva -> snapshot no banco."""
import asyncio
import logging

import httpx

from .ckan import fetch_all_records
from .config import Settings
from .db import Database
from .geo import Geocoder
from .normalize import normalize_records

log = logging.getLogger("vemsus.sync")
_lock = asyncio.Lock()


async def run_sync(
    settings: Settings,
    db: Database,
    ckan_transport: httpx.AsyncBaseTransport | None = None,
    geo_transport: httpx.AsyncBaseTransport | None = None,
) -> dict:
    if _lock.locked():
        return {"ok": False, "error": "sincronização já em andamento"}
    async with _lock:
        log_id = db.log_start()
        diag: dict | None = None
        try:
            records = await fetch_all_records(settings, ckan_transport)
            units, diag = normalize_records(records, settings)
            if not units:
                raise RuntimeError("Nenhuma unidade válida após a normalização.")

            geocoder = Geocoder(settings, db, geo_transport)
            geocoded = 0
            for u in units:
                if u["lat"] is None:
                    coords = await geocoder.geocode(u["address"], u["neighborhood"])
                    if coords:
                        u["lat"], u["lng"], u["geo_source"] = coords[0], coords[1], "geocoded"
                        geocoded += 1
            diag["geocoded"] = geocoded

            without_geo = sum(1 for u in units if u["lat"] is None)
            diag["without_geo"] = without_geo
            db.replace_units(units)  # só troca o snapshot se tudo acima deu certo
            db.log_finish(log_id, True, len(units), without_geo, None, diag)
            log.info("sync ok: %s unidades (%s sem coordenada)", len(units), without_geo)
            return {"ok": True, "units": len(units), "without_geo": without_geo, "geocoded": geocoded}
        except Exception as exc:  # noqa: BLE001 - registramos e mantemos o último snapshot bom
            log.exception("sync falhou")
            db.log_finish(log_id, False, 0, 0, str(exc), diag)
            return {"ok": False, "error": str(exc)}
