import asyncio
import time
from typing import Any

import httpx

AUTH_URL = "https://entreprise.francetravail.fr/connexion/oauth2/access_token?realm=/partenaire"
OFFERS_URL = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"
ROME_SEARCH_URL = "https://api.francetravail.io/partenaire/rome-metiers/v1/metiers/metier/requete"


class FranceTravailError(RuntimeError):
    pass


class FranceTravailClient:
    def __init__(self, client_id: str, client_secret: str) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self._tokens: dict[str, tuple[str, float]] = {}
        self._job_search_cache: dict[str, tuple[float, list[dict[str, str]]]] = {}
        self._rome_lock = asyncio.Lock()
        self._last_rome_request_at = 0.0
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(25.0, connect=10.0))

    async def close(self) -> None:
        await self._client.aclose()

    async def _token(self, scope: str) -> str:
        cached = self._tokens.get(scope)
        if cached and cached[1] > time.time() + 60:
            return cached[0]
        response = await self._request_with_retry(
            "POST",
            AUTH_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": scope,
            },
        )
        payload = response.json()
        token = payload["access_token"]
        self._tokens[scope] = (token, time.time() + payload.get("expires_in", 3600))
        return token

    async def _request_with_retry(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = await self._client.request(method, url, **kwargs)
                if response.status_code == 204:
                    return response
                response.raise_for_status()
                return response
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as exc:
                last_error = exc
                retryable = not isinstance(
                    exc, httpx.HTTPStatusError
                ) or exc.response.status_code in {429, 500, 502, 503, 504}
                if not retryable or attempt == 2:
                    break
                retry_after = 0.0
                if isinstance(exc, httpx.HTTPStatusError):
                    try:
                        retry_after = float(exc.response.headers.get("Retry-After", "0"))
                    except ValueError:
                        retry_after = 0.0
                await asyncio.sleep(max(retry_after, 0.75 * (2**attempt)))
        if isinstance(last_error, httpx.HTTPStatusError):
            status = last_error.response.status_code
            if status == 400:
                raise FranceTravailError(
                    "France Travail a refusé les critères de recherche."
                ) from last_error
            if status in {401, 403}:
                raise FranceTravailError(
                    "Les identifiants France Travail sont invalides ou l'API demandée "
                    "n'est pas activée sur votre application."
                ) from last_error
            if status == 429:
                raise FranceTravailError(
                    "La limite d'appels France Travail est atteinte. "
                    "Réessayez dans quelques instants."
                ) from last_error
        raise FranceTravailError(
            "France Travail est momentanément indisponible. Réessayez dans quelques instants."
        ) from last_error

    async def search_offers(self, query: str) -> list[dict[str, Any]]:
        token = await self._token("api_offresdemploiv2 o2dsoffre")
        params: dict[str, str] = {
            "range": "0-99",
            "sort": "1",
            "motsCles": query,
        }
        response = await self._request_with_retry(
            "GET",
            OFFERS_URL,
            params=params,
            headers={"Authorization": f"Bearer {token}"},
        )
        if response.status_code == 204:
            return []
        return response.json().get("resultats", [])

    async def search_jobs(self, query: str) -> list[dict[str, str]]:
        cache_key = " ".join(query.casefold().split())
        cached = self._job_search_cache.get(cache_key)
        if cached and cached[0] > time.time():
            return [dict(item) for item in cached[1]]
        async with self._rome_lock:
            cached = self._job_search_cache.get(cache_key)
            if cached and cached[0] > time.time():
                return [dict(item) for item in cached[1]]
            delay = 1.0 - (time.monotonic() - self._last_rome_request_at)
            if delay > 0:
                await asyncio.sleep(delay)
            token = await self._token("api_rome-metiersv1 nomenclatureRome")
            try:
                response = await self._request_with_retry(
                    "GET",
                    ROME_SEARCH_URL,
                    params={"q": query},
                    headers={"Authorization": f"Bearer {token}"},
                )
            finally:
                self._last_rome_request_at = time.monotonic()
        payload = response.json()
        raw_results = payload.get("resultats", payload if isinstance(payload, list) else [])
        suggestions: list[dict[str, str]] = []
        seen: set[str] = set()
        for item in raw_results:
            code = str(item.get("code") or item.get("metier", {}).get("code") or "")
            label = str(item.get("libelle") or item.get("metier", {}).get("libelle") or "")
            if code and label and code not in seen:
                seen.add(code)
                suggestions.append({"code": code, "label": label})
        suggestions = suggestions[:8]
        self._job_search_cache[cache_key] = (time.time() + 3_600, suggestions)
        return [dict(item) for item in suggestions]
