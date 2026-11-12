import asyncio

from app.ckan import fetch_all_records
from app.db import Database
from app.geo import validate_coords
from app.normalize import detect_services, detect_unit_type, fold, normalize_records
from app.sync import run_sync

from .conftest import SAMPLE, ckan_transport, nominatim_transport


def by_id(units):
    return {u["id"]: u for u in units}


def test_fold_and_type_detection_uses_word_boundaries():
    assert fold("  Vacinação  ") == "vacinacao"
    assert detect_unit_type("Unidade Ocupacional", "Núcleo")[0] == "Centro de Saúde"  # 'upa' em 'ocupacional' NÃO vira UPA
    assert detect_unit_type("Unidade de Pronto Atendimento", "x") == ("UPA", True)
    assert detect_unit_type("", "USF Alto do Céu") == ("USF", True)


def test_services_are_not_invented():
    assert detect_services("Hospital", ["Internação"]) == []  # sem default 'Atenção Básica'
    assert "Saúde Bucal" in detect_services("USF", ["Saúde bucal", "Odontologia"])
    assert detect_services("USF", []) == ["Atenção Básica"]  # inerente ao tipo, documentado


def test_coordinate_repair(settings):
    assert validate_coords(settings, "-8,0476", "-34,8770") == (-8.0476, -34.877)
    assert validate_coords(settings, "8.12", "34.91") == (-8.12, -34.91)  # sinal perdido
    assert validate_coords(settings, -34.92, -8.05) == (-8.05, -34.92)  # invertidas
    assert validate_coords(settings, -3.5, -38.5) is None  # fora do Recife
    assert validate_coords(settings, 0, 0) is None
    assert validate_coords(settings, None, -34.9) is None


def test_group_rows_by_cnes_and_diagnostics(settings):
    units, diag = normalize_records(SAMPLE, settings)
    u = by_id(units)
    usf = u["cnes-2400001"]
    assert usf["type"] == "USF" and set(usf["services"]) >= {"Vacinação", "Saúde Bucal", "Atenção Básica"}
    assert usf["schedule"] == "Seg a Sex, 8h às 17h"  # horário repetido não duplica
    assert u["cnes-2400002"]["lat"] == -8.119 and u["cnes-2400002"]["geo_source"] == "official"
    assert u["cnes-2400003"]["lat"] == -8.05  # invertida corrigida
    assert u["cnes-2400004"]["geo_source"] == "missing" and u["cnes-2400004"]["address"] == "Rua D, 7"
    assert u["cnes-2400005"]["lat"] is None  # fora da caixa
    assert diag["rows_skipped_excluded_type"] == 1 and diag["rows_skipped_no_name"] == 1
    assert "Unidade Ocupacional" in diag["unmapped_type_values"]
    assert not any(x["name"].startswith("Academia") for x in units)


def test_pagination_and_auth_header(settings):
    big = [{"nome_oficial": f"U{i}"} for i in range(2500)]
    calls = []
    settings.ckan_page_size, settings.ckan_api_token = 1000, "segredo"
    recs = asyncio.run(fetch_all_records(settings, ckan_transport(big, calls)))
    assert len(recs) == 2500 and [c[1]["offset"] for c in calls] == [0, 1000, 2000]
    assert calls[0][2] == "segredo" and calls[0][1]["resource_id"] == settings.ckan_resource_id


def test_sync_geocodes_missing_and_keeps_last_good_snapshot(settings):
    db = Database(settings.database_path)
    geo_calls = []
    r = asyncio.run(run_sync(settings, db, ckan_transport(SAMPLE), nominatim_transport(calls=geo_calls)))
    assert r["ok"] and r["geocoded"] >= 1
    saved = by_id(db.all_units())
    assert saved["cnes-2400004"]["geo_source"] == "geocoded" and saved["cnes-2400004"]["lat"] == -8.1
    assert "contato@" in geo_calls[0][1]  # User-Agent identificado (exigência do Nominatim)

    # segunda rodada usa o cache: sem novas chamadas ao Nominatim
    n = len(geo_calls)
    asyncio.run(run_sync(settings, db, ckan_transport(SAMPLE), nominatim_transport(calls=geo_calls)))
    assert len(geo_calls) == n

    # CKAN fora do ar: o snapshot anterior permanece
    import httpx
    down = httpx.MockTransport(lambda req: httpx.Response(503))
    settings.ckan_timeout_s = 1
    r = asyncio.run(run_sync(settings, db, down))
    assert not r["ok"] and len(db.all_units()) == len(saved)
    assert db.last_sync(only_ok=True)["ok"] == 1


def test_geocoder_result_outside_recife_is_rejected(settings):
    db = Database(settings.database_path)
    r = asyncio.run(run_sync(settings, db, ckan_transport(SAMPLE), nominatim_transport(lat="-23.55", lon="-46.63")))
    assert r["ok"] and by_id(db.all_units())["cnes-2400004"]["lat"] is None
