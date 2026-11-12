import httpx
import pytest

from app.config import Settings

# Linhas no formato REAL do dataset (17 colunas; "endereço" com cedilha; uma linha por unidade x serviço).
def row(**kw):
    base = dict(tipo_unidade="", nome_oficial="", rpa=1, distrito_sanitario=1, microregiao=1, cnes=0, cod_nat="",
                tipo_servico="", especialidade="", como_usar="", horario="", ordem="1", latitude=None, longitude=None)
    base.update(kw)
    base["endereço"] = kw.pop("endereco", "") if "endereco" in kw else base.get("endereço", "")
    base.pop("endereco", None)
    base["fone"] = base.pop("fone", "")
    return base


SAMPLE = [
    row(tipo_unidade="Unidade de Saúde da Família", nome_oficial="USF Alto do Céu", cnes=2400001, endereco="Rua A, 10",
        bairro="Alto do Céu", fone="(81) 3355-0001", tipo_servico="Vacinação", horario="Seg a Sex, 8h às 17h",
        como_usar="Leve cartão de vacina.", latitude=-8.0021, longitude=-34.9412),
    row(tipo_unidade="Unidade de Saúde da Família", nome_oficial="USF Alto do Céu", cnes=2400001, endereco="Rua A, 10",
        bairro="Alto do Céu", tipo_servico="Saúde bucal", especialidade="Odontologia", horario="Seg a Sex, 8h às 17h",
        latitude=-8.0021, longitude=-34.9412),
    # coordenadas com vírgula decimal e sinal positivo (erro de cadastro)
    row(tipo_unidade="Unidade de Pronto Atendimento", nome_oficial="UPA Imbiribeira", cnes=2400002, endereco="Av. B, 500",
        bairro="Imbiribeira", tipo_servico="Urgência e emergência", horario="24 horas", latitude="8,1190", longitude="34,9100"),
    # latitude/longitude invertidas
    row(tipo_unidade="Policlínica", nome_oficial="Policlínica Salomão Kelner", cnes=2400003, endereco="Rua C, 1",
        bairro="Cordeiro", especialidade="Cardiologia", latitude=-34.9200, longitude=-8.0500),
    # sem coordenada e sem endereço
    row(tipo_unidade="Posto de saúde", nome_oficial="UBS Sem Geo", cnes=2400004, endereco="Rua D, 7", bairro="Boa Viagem",
        latitude=None, longitude=None),
    # fora do Recife (ex.: 0,0 / Atlântico)
    row(tipo_unidade="Hospital", nome_oficial="Hospital Fora da Caixa", cnes=2400005, endereco="Rua E", bairro="X",
        latitude=-3.5, longitude=-38.5),
    row(tipo_unidade="Academia da Cidade", nome_oficial="Academia da Cidade Beberibe", cnes=0, endereco="Rua F",
        latitude=-8.0, longitude=-34.9),
    row(tipo_unidade="Unidade Ocupacional", nome_oficial="Núcleo Ocupacional Teste", cnes=2400006, endereco="Rua G",
        bairro="Y", latitude=-8.05, longitude=-34.9),
    row(tipo_unidade="", nome_oficial="", cnes=9),  # sem nome
]


@pytest.fixture
def settings(tmp_path):
    return Settings(database_path=str(tmp_path / "t.db"), sync_on_startup=False, sync_interval_hours=0,
                    static_dir=None, geocode_enabled=True, _env_file=None)


def ckan_transport(records, calls=None):
    def handler(request: httpx.Request) -> httpx.Response:
        import json
        body = json.loads(request.content)
        if calls is not None:
            calls.append((str(request.url), body, request.headers.get("authorization")))
        off, lim = body["offset"], body["limit"]
        return httpx.Response(200, json={"success": True, "result": {"records": records[off:off + lim], "total": len(records)}})
    return httpx.MockTransport(handler)


def nominatim_transport(lat="-8.1000", lon="-34.9000", calls=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append((str(request.url), request.headers.get("user-agent")))
        return httpx.Response(200, json=[{"lat": lat, "lon": lon}] if lat else [])
    return httpx.MockTransport(handler)
