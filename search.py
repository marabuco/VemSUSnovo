"""Busca e ranking. Corrige o protótipo: termo vazio não pontua, acentos são ignorados,
várias palavras funcionam, e o score é calculado uma vez por unidade."""
import math

from .normalize import NO_ADDRESS, fold
from .synonyms import SERVICE_SYNONYMS

STOPWORDS = {"de", "da", "do", "das", "dos", "e", "em", "na", "no", "para", "por", "um", "uma", "com", "perto"}
CHILD_SERVICES = {"Saúde da Criança", "Vacinação", "Puericultura", "Saúde Bucal"}


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    d_lat, d_lng = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(d_lat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lng / 2) ** 2
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _terms(query: str) -> tuple[str, list[str], set[str]]:
    """(frase normalizada, palavras, serviços implícitos). Aceita 'dentista', 'saude mental', 'vacina crianca'."""
    phrase = fold(query)
    words = [w for w in phrase.split(" ") if len(w) >= 2 and w not in STOPWORDS]
    wanted: set[str] = set(SERVICE_SYNONYMS.get(phrase, []))
    for w in words:
        wanted.update(SERVICE_SYNONYMS.get(w, []))
    return phrase, words, wanted


def score_unit(unit: dict, phrase: str, words: list[str], wanted: set[str], distance_km: float | None) -> int:
    score = 0
    if phrase:
        svc_folded = [fold(s) for s in unit["services"]]
        if wanted & set(unit["services"]) or phrase in svc_folded:
            score += 50
        elif any(w in s for w in words for s in svc_folded):
            score += 30
        if phrase in fold(unit["name"]) or any(w in fold(unit["name"]) for w in words):
            score += 20
    if unit.get("schedule"):
        score += 10
    if unit.get("phone"):
        score += 5
    if unit["address"] != NO_ADDRESS:
        score += 10
    if distance_km is not None:
        score += 20 if distance_km < 2 else 10 if distance_km < 5 else 0
    return score


def _matches_text(unit: dict, phrase: str, words: list[str], wanted: set[str]) -> bool:
    haystack = " ".join([fold(unit["name"]), fold(unit.get("neighborhood")), fold(unit["address"]),
                         " ".join(fold(s) for s in unit["services"])])
    if phrase in haystack or wanted & set(unit["services"]):
        return True
    return any(w in haystack for w in words)


def search_units(
    units: list[dict],
    query: str = "",
    services: list[str] | None = None,
    unit_type: str | None = None,
    child_mode: bool = False,
    lat: float | None = None,
    lng: float | None = None,
    limit: int = 200,
) -> tuple[int, list[dict]]:
    phrase, words, wanted = _terms(query)
    results: list[tuple[int, float | None, dict]] = []
    for u in units:
        if u["lat"] is None or u["lng"] is None:
            continue
        if child_mode and not CHILD_SERVICES & set(u["services"]):
            continue
        if unit_type and u["type"] != unit_type:
            continue
        if services and not all(s in u["services"] for s in services):
            continue
        if phrase and not _matches_text(u, phrase, words, wanted):
            continue
        dist = haversine_km(lat, lng, u["lat"], u["lng"]) if lat is not None and lng is not None else None
        results.append((score_unit(u, phrase, words, wanted, dist), dist, u))

    results.sort(key=lambda t: (-t[0], t[1] if t[1] is not None else 1e9, t[2]["name"]))
    out = []
    for _score, dist, u in results[:limit]:
        item = public_unit(u)
        if dist is not None:
            item["distanceKm"] = round(dist, 2)
        out.append(item)
    return len(results), out


def public_unit(u: dict) -> dict:
    """Formato idêntico ao HealthUnit do frontend (types.ts)."""
    return {
        "id": u["id"], "cnes": u.get("cnes"), "name": u["name"], "type": u["type"], "address": u["address"],
        "neighborhood": u.get("neighborhood") or "", "phone": u.get("phone") or None,
        "schedule": u.get("schedule") or None, "lat": u["lat"], "lng": u["lng"], "services": u["services"],
        "beforeVisit": u.get("before_visit") or None, "status": "active",
        "dataSource": "official", "geoSource": u["geo_source"],
    }
