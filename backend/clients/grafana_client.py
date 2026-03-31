"""Async Grafana API client for the Observability KPI Reporting Application.

Provides authenticated access to Grafana REST endpoints including health checks,
datasource management, dashboard retrieval, and datasource proxy queries.
"""

from __future__ import annotations

import logging
from typing import Any, Self

import httpx

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 30.0


class GrafanaAPIError(Exception):
    """Raised when a Grafana API request fails.

    Attributes:
        status_code: HTTP status code returned by Grafana (0 if no response).
        message: Human-readable error description.
    """

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        self.message = message
        super().__init__(f"Grafana API error {status_code}: {message}")


class GrafanaClient:
    """Async HTTP client for the Grafana REST API.

    Usage::

        async with GrafanaClient(grafana_url="https://grafana.example.com", token="...") as client:
            health = await client.health_check()
            datasources = await client.get_datasources()
    """

    def __init__(self, grafana_url: str, token: str) -> None:
        """Initialise the client.

        Args:
            grafana_url: Base URL of the Grafana instance (no trailing slash).
            token: Grafana API / Service-Account token used for Bearer auth.
        """
        self._base_url = grafana_url.rstrip("/")
        self._token = token
        self._client: httpx.AsyncClient | None = None

    # ------------------------------------------------------------------
    # Async context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> Self:
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=httpx.Timeout(DEFAULT_TIMEOUT_SECONDS),
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_client(self) -> httpx.AsyncClient:
        """Return the active ``httpx.AsyncClient``, raising if not initialised."""
        if self._client is None:
            raise RuntimeError(
                "GrafanaClient is not initialised. "
                "Use it as an async context manager: `async with GrafanaClient(...) as client:`"
            )
        return self._client

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        """Send an HTTP request and return the parsed JSON response.

        Raises:
            GrafanaAPIError: On any non-2xx response or transport failure.
        """
        client = self._ensure_client()
        # Intentionally avoid logging the token or full headers.
        logger.debug("Grafana %s %s params=%s", method, path, params)

        try:
            response = await client.request(
                method,
                path,
                params=params,
                json=json_body,
            )
        except httpx.TimeoutException as exc:
            raise GrafanaAPIError(
                status_code=0,
                message=f"Request to {path} timed out: {exc}",
            ) from exc
        except httpx.HTTPError as exc:
            raise GrafanaAPIError(
                status_code=0,
                message=f"Transport error for {path}: {exc}",
            ) from exc

        if not response.is_success:
            body_text = response.text[:500]  # truncate large error bodies
            raise GrafanaAPIError(
                status_code=response.status_code,
                message=f"{method} {path} failed: {body_text}",
            )

        # Some Grafana endpoints (e.g. health) may return non-JSON.
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            return response.json()
        return {"raw": response.text}

    # ------------------------------------------------------------------
    # Public API methods
    # ------------------------------------------------------------------

    async def health_check(self) -> dict[str, Any]:
        """Check Grafana instance health.

        Returns:
            Parsed JSON response from ``GET /api/health``.
        """
        return await self._request("GET", "/api/health")

    async def get_datasources(self) -> list[dict[str, Any]]:
        """List all configured datasources.

        Returns:
            A list of datasource objects from ``GET /api/datasources``.
        """
        return await self._request("GET", "/api/datasources")

    async def get_datasource(self, uid: str) -> dict[str, Any]:
        """Retrieve a single datasource by UID.

        Args:
            uid: The datasource UID.

        Returns:
            Datasource object from ``GET /api/datasources/uid/{uid}``.
        """
        return await self._request("GET", f"/api/datasources/uid/{uid}")

    async def query_datasource(
        self, datasource_uid: str, query: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute a query against a datasource via the Grafana unified query API.

        Args:
            datasource_uid: UID of the target datasource.
            query: Full query payload conforming to the Grafana datasource query
                   schema (``POST /api/ds/query``).

        Returns:
            Parsed JSON result from Grafana.
        """
        payload: dict[str, Any] = {
            "queries": [
                {
                    "datasourceId": 0,  # will be resolved by uid
                    "datasource": {"uid": datasource_uid},
                    **query,
                }
            ],
        }
        return await self._request("POST", "/api/ds/query", json_body=payload)

    async def get_dashboard(self, uid: str) -> dict[str, Any]:
        """Fetch a dashboard by UID.

        Args:
            uid: The dashboard UID.

        Returns:
            Dashboard model from ``GET /api/dashboards/uid/{uid}``.
        """
        return await self._request("GET", f"/api/dashboards/uid/{uid}")

    async def search_dashboards(self, query: str) -> list[dict[str, Any]]:
        """Search dashboards by title or tag.

        Args:
            query: Free-text search term.

        Returns:
            List of matching dashboard stubs from ``GET /api/search``.
        """
        return await self._request("GET", "/api/search", params={"query": query})
