import asyncio
import logging
import secrets
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import Settings, get_settings
from .db import Database
from .search import public_unit, search_units
from .sync import run_sync

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("vemsus")

UNIT_TYPES = ["USF", "UBS", "Centro de Saúde", "Policlínica", "CAPS", "UPA", "SAMU", "Maternidade", "Hospital", "Centro Especializado"]
SERVICE_TAGS = [
    "Vacinação", "Urgência", "Atenção Básica", "Saúde Mental", "Saúde Bucal", "Saúde da Criança", "Saúde da Mulher",
    "Saúde do Idoso", "Farmácia", "Exames", "Curativos", "Pré-natal", "Planejamento Familiar", "Doenças Crônicas",
    "Reabilitação", "Especialidades", "Puericultura", "Hipertensão e Diabetes",
]


class State:
    db: Database
    units: list[dict] = []

    def reload(self) -> None:
        self.units = self.db.all_units()


def create_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or get_settings()
    state = State()

    async def _periodic():
        while True:
            await asyncio.sleep(cfg.sync_interval_hours * 3600)
            await run_sync(cfg, state.db)
            state.reload()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        state.db = Database(cfg.database_path)
        state.reload()
        tasks = []
        if cfg.sync_on_startup:
            async def first():
                await run_sync(cfg, state.db)
                state.reload()
            tasks.append(asyncio.create_task(first()))
        if cfg.sync_interval_hours:
            tasks.append(asyncio.create_task(_periodic()))
        yield
        for t in tasks:
            t.cancel()

    app = FastAPI(title="VemSUS API", version="1.0.0", lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.state.vemsus = state
    app.add_middleware(CORSMiddleware, allow_origins=cfg.cors_origins, allow_methods=["GET"], allow_headers=["*"])

    # --- limite de requisições por IP (só em memória; nenhum IP é gravado) e cabeçalhos de segurança
    hits: dict[str, deque] = defaultdict(deque)

    @app.middleware("http")
    async def guard(request: Request, call_next):
        if request.url.path.startswith("/api/"):
            ip = request.client.host if request.client else "?"
            if cfg.trust_proxy and request.headers.get("x-forwarded-for"):
                ip = request.headers["x-forwarded-for"].split(",")[0].strip()
            now, window = time.monotonic(), hits[ip]
            while window and now - window[0] > 60:
                window.popleft()
            if len(window) >= cfg.rate_limit_per_minute:
                return JSONResponse({"detail": "Muitas requisições. Tente de novo em instantes."}, status_code=429)
            window.append(now)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "geolocation=(self), camera=(), microphone=()"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"  # a query pode conter a localização do usuário
        return response

    @app.get("/api/health")
    def health():
        return {"status": "ok", "units_loaded": len(state.units)}

    @app.get("/api/units")
    def list_units(
        q: str = Query("", max_length=100),
        services: list[str] = Query(default=[]),
        type: str | None = Query(default=None, max_length=40),
        child: bool = False,
        lat: float | None = Query(default=None, ge=-90, le=90),
        lng: float | None = Query(default=None, ge=-180, le=180),
        limit: int = Query(default=200, ge=1, le=1000),
    ):
        if (lat is None) != (lng is None):
            raise HTTPException(422, "Informe lat e lng juntos.")
        if type and type not in UNIT_TYPES:
            raise HTTPException(422, "Tipo de unidade inválido.")
        bad = [s for s in services if s not in SERVICE_TAGS]
        if bad:
            raise HTTPException(422, f"Serviço desconhecido: {bad[0]}")
        total, units = search_units(state.units, q, services, type, child, lat, lng, limit)
        return {"total": total, "units": units}

    @app.get("/api/units/{unit_id}")
    def get_unit(unit_id: str):
        for u in state.units:
            if u["id"] == unit_id and u["lat"] is not None:
                return public_unit(u)
        raise HTTPException(404, "Unidade não encontrada.")

    @app.get("/api/services")
    def services():
        return {"services": SERVICE_TAGS, "unitTypes": UNIT_TYPES}

    @app.get("/api/meta")
    def meta():
        last = state.db.last_sync(only_ok=True)
        return {
            "source": "Prefeitura do Recife — Portal de Dados Abertos",
            "dataset": "Rede de atenção à saúde no Recife",
            "datasetUrl": f"{cfg.ckan_base_url}/dataset/rede-de-atencao-a-saude-no-recife",
            "license": "ODbL — Open Data Commons Open Database License",
            "unitsServed": sum(1 for u in state.units if u["lat"] is not None),
            "unitsWithoutLocation": sum(1 for u in state.units if u["lat"] is None),
            "approximateLocation": sum(1 for u in state.units if u["geo_source"] == "geocoded"),
            "lastSync": last["finished_at"] if last else None,
            "ready": bool(state.units),
        }

    def require_admin(x_admin_token: str | None = Header(default=None)):
        if not cfg.admin_token or not x_admin_token or not secrets.compare_digest(x_admin_token, cfg.admin_token):
            raise HTTPException(403, "Não autorizado.")

    @app.post("/api/admin/sync", dependencies=[Depends(require_admin)])
    async def admin_sync():
        result = await run_sync(cfg, state.db)
        state.reload()
        return result

    @app.get("/api/admin/diagnostico", dependencies=[Depends(require_admin)])
    def diagnostico():
        """Mostra o que o normalizador não reconheceu (valores de tipo_unidade, coordenadas inválidas...)."""
        return state.db.last_sync() or {}

    static = Path(cfg.static_dir).resolve() if cfg.static_dir else None
    if static and static.is_dir():
        app.mount("/", StaticFiles(directory=static, html=True), name="site")
    return app


app = create_app()
