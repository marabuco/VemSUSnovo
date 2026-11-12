import asyncio

from fastapi.testclient import TestClient

from app.main import create_app
from app.normalize import normalize_records
from app.search import search_units

from .conftest import SAMPLE


def units(settings):
    u, _ = normalize_records(SAMPLE, settings)
    return [x for x in u if x["lat"] is not None]


def names(res):
    return [x["name"] for x in res[1]]


def test_empty_query_does_not_boost_everything(settings):
    from app.search import score_unit
    us = units(settings)
    total, _ = search_units(us, "")
    assert total == 4  # só as com coordenada válida; unidades sem localização não entram
    bare = next(u for u in us if u["name"].startswith("Núcleo"))
    assert score_unit(bare, "", [], set(), None) == 10  # só endereço oficial; protótipo dava +30 a todos com termo vazio


def test_accent_insensitive_synonyms_and_multiword(settings):
    us = units(settings)
    assert names(search_units(us, "vacinacao"))[0] == "USF Alto do Céu"
    assert "USF Alto do Céu" in names(search_units(us, "dentista"))
    assert names(search_units(us, "pronto socorro")) [0] == "UPA Imbiribeira"
    assert search_units(us, "xyzabc")[0] == 0


def test_filters_and_distance_ordering(settings):
    us = units(settings)
    assert names(search_units(us, unit_type="UPA")) == ["UPA Imbiribeira"]
    assert search_units(us, services=["Vacinação", "Urgência"])[0] == 0  # precisa ter TODOS
    total, res = search_units(us, "", lat=-8.12, lng=-34.91)
    assert res[0]["name"] == "UPA Imbiribeira" and res[0]["distanceKm"] < 1  # <2 km: +20 e vem primeiro
    assert search_units(us, child_mode=True)[1][0]["name"] == "USF Alto do Céu"


def test_api_endpoints(settings):
    app = create_app(settings)
    with TestClient(app) as client:
        state = app.state.vemsus
        u, _ = normalize_records(SAMPLE, settings)
        state.db.replace_units(u)
        state.reload()
        assert client.get("/api/health").json()["units_loaded"] == len(u)
        body = client.get("/api/units", params={"q": "vacina", "lat": -8.0, "lng": -34.94}).json()
        assert body["units"][0]["id"] == "cnes-2400001" and "distanceKm" in body["units"][0]
        assert body["units"][0]["dataSource"] == "official" and "latitude" not in body["units"][0]
        assert client.get("/api/units", params={"lat": -8.0}).status_code == 422
        assert client.get("/api/units", params={"type": "Pizzaria"}).status_code == 422
        assert client.get("/api/units", params={"lat": 999, "lng": 0}).status_code == 422
        assert client.get("/api/units/cnes-2400001").status_code == 200
        assert client.get("/api/units/cnes-2400004").status_code == 404  # sem coordenada não é exposta
        assert client.get("/api/units").headers["cache-control"] == "no-store"
        meta = client.get("/api/meta").json()
        assert meta["unitsWithoutLocation"] >= 1 and "ODbL" in meta["license"]
        assert client.post("/api/admin/sync").status_code == 403  # sem ADMIN_TOKEN configurado


def test_rate_limit(settings):
    settings.rate_limit_per_minute = 3
    with TestClient(create_app(settings)) as client:
        codes = [client.get("/api/health").status_code for _ in range(5)]
    assert codes == [200, 200, 200, 429, 429]
