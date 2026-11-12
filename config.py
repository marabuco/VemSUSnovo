from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Portal de Dados Abertos do Recife (CKAN) ---
    ckan_base_url: str = "https://dados.recife.pe.gov.br"
    ckan_api_path: str = "/api/3/action"
    ckan_resource_id: str = "c960077b-640c-4cbc-9fac-01be82bf54d9"
    ckan_api_token: str | None = None  # NUNCA vai para o frontend
    ckan_page_size: int = 1000
    ckan_timeout_s: float = 30.0

    # --- Armazenamento / sincronização ---
    database_path: str = "data/vemsus.db"
    sync_on_startup: bool = True
    sync_interval_hours: int = 24

    # --- API ---
    admin_token: str | None = None  # habilita POST /api/admin/sync
    allowed_origins: str = "http://localhost:5173,http://localhost:8443"
    static_dir: str | None = "../frontend/dist"  # serve o site buildado
    trust_proxy: bool = False  # true atrás do Caddy/Nginx (usa X-Forwarded-For)
    rate_limit_per_minute: int = 120

    # --- Georreferenciamento ---
    # Caixa que contém o Recife (+ margem). Coordenadas fora dela são tratadas como erro de cadastro.
    geo_min_lat: float = -8.25
    geo_max_lat: float = -7.85
    geo_min_lng: float = -35.10
    geo_max_lng: float = -34.80
    geocode_enabled: bool = True
    nominatim_url: str = "https://nominatim.openstreetmap.org/search"
    # Política do Nominatim exige identificação real. TROQUE pelo seu contato.
    nominatim_user_agent: str = "VemSUS/1.0 (contato@seudominio.com.br)"
    geocode_max_per_sync: int = 60
    geocode_retry_days: int = 30

    # Tipos que existem no dataset mas não são unidades de atendimento
    exclude_type_patterns: str = "academia da cidade"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
