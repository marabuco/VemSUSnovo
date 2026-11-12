"""Cliente do CKAN do Recife (datastore_search), com paginação e retentativas."""
import asyncio

import httpx

from .config import Settings


class CkanError(RuntimeError):
    pass


async def fetch_all_records(
    settings: Settings, transport: httpx.AsyncBaseTransport | None = None
) -> list[dict]:
    url = f"{settings.ckan_base_url.rstrip('/')}{settings.ckan_api_path}/datastore_search"
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if settings.ckan_api_token:
        headers["Authorization"] = settings.ckan_api_token

    records: list[dict] = []
    offset = 0
    async with httpx.AsyncClient(
        timeout=settings.ckan_timeout_s, transport=transport, follow_redirects=True
    ) as client:
        for _page in range(500):  # trava de segurança
            body = {
                "resource_id": settings.ckan_resource_id,
                "limit": settings.ckan_page_size,
                "offset": offset,
            }
            payload = await _post(client, url, headers, body)
            result = payload.get("result") or {}
            page = result.get("records") or []
            records.extend(page)
            offset += len(page)
            total = result.get("total")
            if not page or (isinstance(total, int) and offset >= total):
                break
    if not records:
        raise CkanError("O CKAN respondeu sem registros.")
    return records


async def _post(client: httpx.AsyncClient, url: str, headers: dict, body: dict) -> dict:
    last: Exception | None = None
    for attempt in range(4):
        try:
            resp = await client.post(url, headers=headers, json=body)
            if resp.status_code >= 500 or resp.status_code == 429:
                raise CkanError(f"HTTP {resp.status_code}")
            if resp.status_code in (401, 403):
                raise CkanError(f"Acesso negado pelo CKAN (HTTP {resp.status_code}). Verifique CKAN_API_TOKEN.")
            resp.raise_for_status()
            data = resp.json()
            if not data.get("success"):
                raise CkanError(f"CKAN retornou success=false: {data.get('error')}")
            return data
        except (httpx.HTTPError, CkanError, ValueError) as exc:
            last = exc
            if isinstance(exc, CkanError) and "negado" in str(exc):
                break  # não adianta tentar de novo
            await asyncio.sleep(0.5 * 2**attempt)
    raise CkanError(f"Falha ao consultar o CKAN: {last}")
