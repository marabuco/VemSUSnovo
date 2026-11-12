"""Transforma as linhas cruas do dataset (uma linha por unidade x serviço) em unidades do VemSUS."""
import hashlib
import re
import unicodedata
from collections import Counter, defaultdict

from .config import Settings
from .geo import validate_coords

NO_ADDRESS = "Informação não disponível na base oficial."


def fold(text) -> str:
    """minúsculas, sem acento, espaços normalizados."""
    if text is None:
        return ""
    txt = unicodedata.normalize("NFKD", str(text))
    txt = "".join(c for c in txt if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", txt).strip().lower()


def clean(text) -> str:
    return re.sub(r"\s+", " ", str(text)).strip() if text is not None else ""


def _row(raw: dict) -> dict:
    """Chaves sem acento ('endereço' -> 'endereco'), para tolerar variações do portal."""
    return {fold(k).replace(" ", "_"): v for k, v in raw.items()}


# ---------------------------------------------------------------- tipo de unidade
# Ordem importa: do mais específico para o mais genérico. Usa palavras inteiras
# (o protótipo usava 'includes', e "upa" casava com "ocupacional").
TYPE_RULES: list[tuple[str, re.Pattern]] = [
    ("SAMU", re.compile(r"\bsamu\b|atendimento movel")),
    ("UPA", re.compile(r"\bupa\b|pronto atend")),
    ("CAPS", re.compile(r"\bcaps\b|psicossocial")),
    ("Maternidade", re.compile(r"maternidade")),
    ("Hospital", re.compile(r"hospital")),
    ("Policlínica", re.compile(r"policlinica")),
    ("USF", re.compile(r"\busf\b|saude da familia|\besf\b")),
    ("UBS", re.compile(r"\bubs\b|unidade basica|posto de saude")),
    ("Centro Especializado", re.compile(r"especializad|\bceo\b|\bcer\b|\bcem\b")),
    ("Centro de Saúde", re.compile(r"centro de saude")),
]


def detect_unit_type(tipo_unidade: str, nome: str) -> tuple[str, bool]:
    """Devolve (tipo, reconhecido). Procura primeiro no campo tipo_unidade, depois no nome."""
    for source in (fold(tipo_unidade), fold(nome)):
        for unit_type, pattern in TYPE_RULES:
            if source and pattern.search(source):
                return unit_type, True
    return "Centro de Saúde", False


# ---------------------------------------------------------------- serviços
SERVICE_RULES: list[tuple[str, re.Pattern]] = [
    ("Vacinação", re.compile(r"vacin|imuniza")),
    ("Urgência", re.compile(r"urgenc|emergenc|pronto atend|pronto.socorro")),
    ("Atenção Básica", re.compile(r"atencao basica|atencao primaria|saude da familia|clinico geral|clinica medica")),
    ("Saúde Mental", re.compile(r"mental|psicolog|psiquiatr|psicossocial")),
    ("Saúde Bucal", re.compile(r"bucal|odonto|dentist|dental")),
    ("Saúde da Criança", re.compile(r"crianca|pediatr|infantil")),
    ("Puericultura", re.compile(r"puericult")),
    ("Saúde da Mulher", re.compile(r"mulher|ginecolog|obstetr")),
    ("Saúde do Idoso", re.compile(r"idoso|geriatr")),
    ("Farmácia", re.compile(r"farmaci|dispensacao")),
    ("Exames", re.compile(r"exame|laborator|ultrassom|ultrasson|radiolog|raio.?x|diagnostic|patologia clinica|mamograf")),
    ("Curativos", re.compile(r"curativo")),
    ("Pré-natal", re.compile(r"pre.?natal")),
    ("Planejamento Familiar", re.compile(r"planejamento (familiar|reprodutivo)")),
    ("Doenças Crônicas", re.compile(r"cronic|hipertens|diabet")),
    ("Hipertensão e Diabetes", re.compile(r"hipertens|diabet")),
    ("Reabilitação", re.compile(r"reabilit|fisioterap|fonoaudi|terapia ocupacional")),
    (
        "Especialidades",
        re.compile(r"especialidade|cardiolog|ortoped|dermatolog|oftalmolog|neurolog|endocrin|urolog|otorrino|reumatolog|nefrolog|gastro|pneumolog"),
    ),
]

# Serviços inerentes ao tipo de unidade (documentado; NÃO é um "default" para todas as unidades).
TYPE_IMPLIED_SERVICES = {
    "USF": ["Atenção Básica"],
    "UBS": ["Atenção Básica"],
    "UPA": ["Urgência"],
    "SAMU": ["Urgência"],
    "CAPS": ["Saúde Mental"],
    "Policlínica": ["Especialidades"],
    "Centro Especializado": ["Especialidades"],
}


def detect_services(unit_type: str, service_texts: list[str]) -> list[str]:
    found: set[str] = set(TYPE_IMPLIED_SERVICES.get(unit_type, []))
    for text in service_texts:
        folded = fold(text)
        for tag, pattern in SERVICE_RULES:
            if pattern.search(folded):
                found.add(tag)
    order = {tag: i for i, (tag, _) in enumerate(SERVICE_RULES)}
    return sorted(found, key=lambda t: order.get(t, 99))


# ---------------------------------------------------------------- agrupamento
def _unique(values: list[str]) -> list[str]:
    seen, out = set(), []
    for v in values:
        key = fold(v)
        if v and key not in seen:
            seen.add(key)
            out.append(v)
    return out


def _unit_key(row: dict) -> str:
    cnes = clean(row.get("cnes"))
    cnes = re.sub(r"\.0+$", "", cnes)  # numeric vindo como 2400030.0
    if cnes and cnes != "0":
        return f"cnes-{cnes}"
    base = f"{fold(row.get('nome_oficial'))}|{fold(row.get('endereco'))}"
    return "h-" + hashlib.sha1(base.encode()).hexdigest()[:12]


def normalize_records(records: list[dict], settings: Settings) -> tuple[list[dict], dict]:
    """Agrupa as linhas por unidade. Devolve (unidades, diagnóstico).
    Unidades sem coordenada válida saem com lat/lng = None (o Geocoder tenta resolver depois)."""
    exclude = [fold(p) for p in settings.exclude_type_patterns.split(",") if p.strip()]
    groups: dict[str, list[dict]] = defaultdict(list)
    diag = {
        "rows": len(records),
        "rows_skipped_no_name": 0,
        "rows_skipped_excluded_type": 0,
        "unmapped_type_values": Counter(),
        "coords_fixed": 0,
        "coords_invalid": 0,
    }

    for raw in records:
        row = _row(raw)
        if not clean(row.get("nome_oficial")):
            diag["rows_skipped_no_name"] += 1
            continue
        if any(p in fold(row.get("tipo_unidade")) for p in exclude):
            diag["rows_skipped_excluded_type"] += 1
            continue
        groups[_unit_key(row)].append(row)

    units: list[dict] = []
    for key, rows in groups.items():
        first = rows[0]
        name = clean(first.get("nome_oficial"))
        tipo_raw = clean(first.get("tipo_unidade"))
        unit_type, recognized = detect_unit_type(tipo_raw, name)
        if not recognized:
            diag["unmapped_type_values"][tipo_raw or "(vazio)"] += 1

        address = next((clean(r.get("endereco")) for r in rows if clean(r.get("endereco"))), "")
        neighborhood = next((clean(r.get("bairro")) for r in rows if clean(r.get("bairro"))), "")
        phone = next((clean(r.get("fone")) for r in rows if clean(r.get("fone"))), "")
        schedule = " · ".join(_unique([clean(r.get("horario")) for r in rows]))
        how_to = " ".join(_unique([clean(r.get("como_usar")) for r in rows]))

        service_texts = [clean(r.get("tipo_servico")) for r in rows] + [clean(r.get("especialidade")) for r in rows]
        services = detect_services(unit_type, service_texts)

        coords = None
        for r in rows:
            coords = validate_coords(settings, r.get("latitude"), r.get("longitude"))
            if coords:
                raw_lat = r.get("latitude")
                if str(raw_lat).strip().replace(",", ".") != str(coords[0]):
                    diag["coords_fixed"] += 1
                break
        if not coords:
            diag["coords_invalid"] += 1

        units.append(
            {
                "id": key,
                "cnes": key[5:] if key.startswith("cnes-") else None,
                "name": name,
                "type": unit_type,
                "address": address or NO_ADDRESS,
                "neighborhood": neighborhood,
                "phone": phone or None,
                "schedule": schedule or None,
                "lat": coords[0] if coords else None,
                "lng": coords[1] if coords else None,
                "geo_source": "official" if coords else "missing",
                "services": services,
                "before_visit": how_to or None,
            }
        )

    diag["unmapped_type_values"] = dict(diag["unmapped_type_values"].most_common(30))
    diag["units"] = len(units)
    return units, diag
