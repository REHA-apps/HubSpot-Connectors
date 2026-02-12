from typing import Any, Dict, Optional
import httpx

class BaseClient:
    """Base async client for all connectors with common HTTP methods."""

    base_url: str
    headers: Dict[str, str]

    def __init__(self, base_url: str, headers: Optional[Dict[str, str]] = None):
        self.base_url = base_url
        self.headers = headers or {}

    async def request(self, method: str, path: str, **kwargs) -> dict[str, Any]:
        url = f"{self.base_url}{path.lstrip('/')}"
        async with httpx.AsyncClient() as client:
            response = await client.request(method, url, headers=self.headers, **kwargs)
            response.raise_for_status()
            return response.json()

    async def get(self, path: str, params: Optional[Dict[str, Any]] = None):
        return await self.request("GET", path, params=params)

    async def post(self, path: str, data: Optional[Dict[str, Any]] = None):
        return await self.request("POST", path, json=data)
