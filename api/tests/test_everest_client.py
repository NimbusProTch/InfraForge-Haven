"""Unit tests for Percona Everest REST API client."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.everest_client import (
    ENGINE_MAP,
    TIER_CONFIG,
    EverestClient,
)

# ---------------------------------------------------------------------------
# ENGINE_MAP and TIER_CONFIG
# ---------------------------------------------------------------------------


class TestEngineMap:
    def test_postgres_aliases(self):
        assert ENGINE_MAP["postgres"] == "postgresql"
        assert ENGINE_MAP["postgresql"] == "postgresql"

    def test_mysql_aliases(self):
        assert ENGINE_MAP["mysql"] == "pxc"
        assert ENGINE_MAP["pxc"] == "pxc"

    def test_mongodb_aliases(self):
        assert ENGINE_MAP["mongodb"] == "psmdb"
        assert ENGINE_MAP["mongo"] == "psmdb"
        assert ENGINE_MAP["psmdb"] == "psmdb"

    def test_unsupported_engine_not_in_map(self):
        assert "redis" not in ENGINE_MAP
        assert "rabbitmq" not in ENGINE_MAP


class TestTierConfig:
    def test_dev_tier(self):
        cfg = TIER_CONFIG["dev"]
        assert cfg["replicas"] == 1
        assert cfg["storage"] == "2Gi"
        assert cfg["cpu"] == "1"
        assert cfg["memory"] == "512Mi"

    def test_prod_tier(self):
        cfg = TIER_CONFIG["prod"]
        assert cfg["replicas"] == 3
        assert cfg["storage"] == "20Gi"
        assert cfg["cpu"] == "2"
        assert cfg["memory"] == "4Gi"


# ---------------------------------------------------------------------------
# EverestClient
# ---------------------------------------------------------------------------


def _mock_response(status_code: int = 200, json_data: dict | None = None) -> MagicMock:
    """Create a mock httpx.Response."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            message=f"HTTP {status_code}",
            request=MagicMock(),
            response=resp,
        )
    return resp


class TestEverestClientInit:
    def test_default_url(self):
        """Default URL comes from settings (env var or config default)."""
        client = EverestClient()
        assert client._base_url  # Non-empty when EVEREST_URL is set

    def test_custom_url(self):
        client = EverestClient(base_url="http://localhost:9999/")
        assert client._base_url == "http://localhost:9999"  # trailing slash stripped

    def test_is_configured(self):
        client = EverestClient(base_url="http://localhost:9999")
        assert client.is_configured() is True

    def test_is_configured_empty(self):
        client = EverestClient(base_url="")
        assert client.is_configured() is False


class TestGetToken:
    @pytest.mark.asyncio
    async def test_get_token_success(self):
        client = EverestClient(base_url="http://fake:8080")
        mock_resp = _mock_response(200, {"token": "jwt-abc-123"})

        mock_http = AsyncMock()
        mock_http.post.return_value = mock_resp
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.everest_client.httpx.AsyncClient", return_value=mock_http):
            token = await client._get_token()

        assert token == "jwt-abc-123"
        mock_http.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_token_cached(self):
        client = EverestClient(base_url="http://fake:8080")
        client._token = "cached-token"

        token = await client._get_token()
        assert token == "cached-token"

    @pytest.mark.asyncio
    async def test_get_token_failure(self):
        client = EverestClient(base_url="http://fake:8080")
        mock_resp = _mock_response(401, {"message": "bad credentials"})

        mock_http = AsyncMock()
        mock_http.post.return_value = mock_resp
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.everest_client.httpx.AsyncClient", return_value=mock_http):
            with pytest.raises(httpx.HTTPStatusError):
                await client._get_token()


class TestRequest:
    @pytest.mark.asyncio
    async def test_request_adds_bearer_token(self):
        client = EverestClient(base_url="http://fake:8080")
        client._token = "my-token"

        mock_resp = _mock_response(200, {"items": []})
        mock_http = AsyncMock()
        mock_http.request.return_value = mock_resp
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.everest_client.httpx.AsyncClient", return_value=mock_http):
            result = await client._request("GET", "/v1/test")

        assert result == {"items": []}
        call_kwargs = mock_http.request.call_args
        assert call_kwargs.kwargs["headers"]["Authorization"] == "Bearer my-token"

    @pytest.mark.asyncio
    async def test_request_retries_on_401(self):
        client = EverestClient(base_url="http://fake:8080")
        client._token = "expired-token"

        # First call returns 401, after re-auth returns 200
        resp_401 = MagicMock(spec=httpx.Response)
        resp_401.status_code = 401

        resp_200 = _mock_response(200, {"data": "ok"})

        mock_http = AsyncMock()
        mock_http.request.side_effect = [resp_401, resp_200]
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)

        # Mock _get_token to return new token after reset
        new_token_resp = _mock_response(200, {"token": "new-token"})
        mock_http.post.return_value = new_token_resp

        with patch("app.services.everest_client.httpx.AsyncClient", return_value=mock_http):
            result = await client._request("GET", "/v1/test")

        assert result == {"data": "ok"}
        assert client._token == "new-token"

    @pytest.mark.asyncio
    async def test_request_204_returns_empty_dict(self):
        client = EverestClient(base_url="http://fake:8080")
        client._token = "my-token"

        mock_resp = _mock_response(204)
        mock_http = AsyncMock()
        mock_http.request.return_value = mock_resp
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.everest_client.httpx.AsyncClient", return_value=mock_http):
            result = await client._request("DELETE", "/v1/test")

        assert result == {}


class TestCreateDatabase:
    @pytest.mark.asyncio
    async def test_create_postgres(self):
        client = EverestClient(base_url="http://fake:8080")
        client._token = "my-token"

        mock_resp = _mock_response(200, {"metadata": {"name": "my-db"}, "status": {}})
        mock_http = AsyncMock()
        mock_http.request.return_value = mock_resp
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.everest_client.httpx.AsyncClient", return_value=mock_http):
            result = await client.create_database("my-db", "postgres", tier="dev")

        assert result["metadata"]["name"] == "my-db"
        call_kwargs = mock_http.request.call_args
        body = call_kwargs.kwargs["json"]
        assert body["spec"]["engine"]["type"] == "postgresql"
        assert body["spec"]["engine"]["replicas"] == 1
        assert body["spec"]["engine"]["storage"]["size"] == "2Gi"

    @pytest.mark.asyncio
    async def test_create_mysql_prod(self):
        client = EverestClient(base_url="http://fake:8080")
        client._token = "my-token"

        mock_resp = _mock_response(200, {"metadata": {"name": "my-mysql"}})
        mock_http = AsyncMock()
        mock_http.request.return_value = mock_resp
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.everest_client.httpx.AsyncClient", return_value=mock_http):
            result = await client.create_database("my-mysql", "mysql", tier="prod")

        call_kwargs = mock_http.request.call_args
        body = call_kwargs.kwargs["json"]
        assert body["spec"]["engine"]["type"] == "pxc"
        assert body["spec"]["engine"]["replicas"] == 3
        assert body["spec"]["proxy"]["replicas"] == 3

    @pytest.mark.asyncio
    async def test_create_mongodb(self):
        client = EverestClient(base_url="http://fake:8080")
        client._token = "my-token"

        mock_resp = _mock_response(200, {"metadata": {"name": "my-mongo"}})
        mock_http = AsyncMock()
        mock_http.request.return_value = mock_resp
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.everest_client.httpx.AsyncClient", return_value=mock_http):
            result = await client.create_database("my-mongo", "mongodb", tier="dev")

        call_kwargs = mock_http.request.call_args
        body = call_kwargs.kwargs["json"]
        assert body["spec"]["engine"]["type"] == "psmdb"

    @pytest.mark.asyncio
    async def test_create_with_version(self):
        client = EverestClient(base_url="http://fake:8080")
        client._token = "my-token"

        mock_resp = _mock_response(200, {"metadata": {"name": "my-db"}})
        mock_http = AsyncMock()
        mock_http.request.return_value = mock_resp
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.everest_client.httpx.AsyncClient", return_value=mock_http):
            await client.create_database("my-db", "postgres", version="16.2")

        call_kwargs = mock_http.request.call_args
        body = call_kwargs.kwargs["json"]
        assert body["spec"]["engine"]["version"] == "16.2"

    @pytest.mark.asyncio
    async def test_create_unsupported_engine_raises(self):
        client = EverestClient(base_url="http://fake:8080")
        with pytest.raises(ValueError, match="Unsupported engine type: redis"):
            await client.create_database("my-redis", "redis")


class TestGetDatabase:
    @pytest.mark.asyncio
    async def test_get_database(self):
        client = EverestClient(base_url="http://fake:8080")
        client._token = "my-token"

        db_data = {"metadata": {"name": "my-db"}, "status": {"status": "ready"}}
        mock_resp = _mock_response(200, db_data)
        mock_http = AsyncMock()
        mock_http.request.return_value = mock_resp
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.everest_client.httpx.AsyncClient", return_value=mock_http):
            result = await client.get_database("my-db")

        assert result["status"]["status"] == "ready"


class TestDeleteDatabase:
    @pytest.mark.asyncio
    async def test_delete_database(self):
        client = EverestClient(base_url="http://fake:8080")
        client._token = "my-token"

        mock_resp = _mock_response(204)
        mock_http = AsyncMock()
        mock_http.request.return_value = mock_resp
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.everest_client.httpx.AsyncClient", return_value=mock_http):
            result = await client.delete_database("my-db")

        assert result == {}


class TestListDatabases:
    @pytest.mark.asyncio
    async def test_list_databases(self):
        client = EverestClient(base_url="http://fake:8080")
        client._token = "my-token"

        mock_resp = _mock_response(200, {"items": [{"metadata": {"name": "db1"}}, {"metadata": {"name": "db2"}}]})
        mock_http = AsyncMock()
        mock_http.request.return_value = mock_resp
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.everest_client.httpx.AsyncClient", return_value=mock_http):
            result = await client.list_databases()

        assert len(result) == 2
        assert result[0]["metadata"]["name"] == "db1"

    @pytest.mark.asyncio
    async def test_list_databases_empty(self):
        client = EverestClient(base_url="http://fake:8080")
        client._token = "my-token"

        mock_resp = _mock_response(200, {"items": []})
        mock_http = AsyncMock()
        mock_http.request.return_value = mock_resp
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.everest_client.httpx.AsyncClient", return_value=mock_http):
            result = await client.list_databases()

        assert result == []


class TestGetDatabaseStatus:
    @pytest.mark.asyncio
    async def test_status_ready(self):
        client = EverestClient(base_url="http://fake:8080")
        client._token = "my-token"

        mock_resp = _mock_response(200, {"status": {"status": "ready"}})
        mock_http = AsyncMock()
        mock_http.request.return_value = mock_resp
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.everest_client.httpx.AsyncClient", return_value=mock_http):
            status = await client.get_database_status("my-db")

        assert status == "ready"

    @pytest.mark.asyncio
    async def test_status_not_found(self):
        client = EverestClient(base_url="http://fake:8080")
        client._token = "my-token"

        resp_404 = MagicMock(spec=httpx.Response)
        resp_404.status_code = 404
        error = httpx.HTTPStatusError(message="Not Found", request=MagicMock(), response=resp_404)

        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 404
        mock_resp.raise_for_status.side_effect = error

        mock_http = AsyncMock()
        mock_http.request.return_value = mock_resp
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.everest_client.httpx.AsyncClient", return_value=mock_http):
            status = await client.get_database_status("missing-db")

        assert status == "not_found"

    @pytest.mark.asyncio
    async def test_status_unknown_when_empty(self):
        client = EverestClient(base_url="http://fake:8080")
        client._token = "my-token"

        mock_resp = _mock_response(200, {"status": {}})
        mock_http = AsyncMock()
        mock_http.request.return_value = mock_resp
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.everest_client.httpx.AsyncClient", return_value=mock_http):
            status = await client.get_database_status("my-db")

        assert status == "unknown"


class TestGetCredentials:
    @pytest.mark.asyncio
    async def test_get_credentials_returns_hostname_and_port(self):
        """Everest API returns hostname/port but not username/password (those are in K8s secrets)."""
        client = EverestClient(base_url="http://fake:8080")
        client._token = "my-token"

        mock_resp = _mock_response(
            200,
            {
                "status": {
                    "hostname": "my-db-pgbouncer.everest.svc",
                    "port": 5432,
                }
            },
        )
        mock_http = AsyncMock()
        mock_http.request.return_value = mock_resp
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.everest_client.httpx.AsyncClient", return_value=mock_http):
            creds = await client.get_credentials("my-db")

        assert creds["hostname"] == "my-db-pgbouncer.everest.svc"
        assert creds["port"] == "5432"


class TestUpdateDatabase:
    @pytest.mark.asyncio
    async def test_update_storage(self):
        client = EverestClient(base_url="http://fake:8080")
        client._token = "my-token"

        # GET returns current state
        current = {
            "metadata": {"name": "my-db", "resourceVersion": "12345"},
            "spec": {
                "engine": {
                    "type": "postgresql",
                    "replicas": 1,
                    "storage": {"size": "1Gi"},
                    "resources": {"cpu": "600m", "memory": "512Mi"},
                },
                "proxy": {"replicas": 1},
            },
        }
        updated = {**current, "metadata": {**current["metadata"], "resourceVersion": "12346"}}
        updated["spec"] = {**current["spec"]}

        get_resp = _mock_response(200, current)
        put_resp = _mock_response(200, updated)

        mock_http = AsyncMock()
        mock_http.request.side_effect = [get_resp, put_resp]
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.everest_client.httpx.AsyncClient", return_value=mock_http):
            result = await client.update_database("my-db", storage="2Gi")

        # Should have made GET then PUT
        assert mock_http.request.call_count == 2
        get_call, put_call = mock_http.request.call_args_list
        assert get_call.args[0] == "GET"
        assert put_call.args[0] == "PUT"

        # PUT body should include resourceVersion
        put_body = put_call.kwargs["json"]
        assert put_body["metadata"]["resourceVersion"] == "12345"

    @pytest.mark.asyncio
    async def test_update_multiple_fields(self):
        client = EverestClient(base_url="http://fake:8080")
        client._token = "my-token"

        current = {
            "metadata": {"name": "my-db", "resourceVersion": "100"},
            "spec": {
                "engine": {
                    "type": "postgresql",
                    "replicas": 1,
                    "storage": {"size": "1Gi"},
                    "resources": {"cpu": "600m", "memory": "512Mi"},
                },
                "proxy": {"replicas": 1},
            },
        }

        get_resp = _mock_response(200, current)
        put_resp = _mock_response(200, current)

        mock_http = AsyncMock()
        mock_http.request.side_effect = [get_resp, put_resp]
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.everest_client.httpx.AsyncClient", return_value=mock_http):
            await client.update_database("my-db", replicas=3, cpu="2", memory="4Gi")

        put_body = mock_http.request.call_args_list[1].kwargs["json"]
        assert put_body["spec"]["engine"]["replicas"] == 3
        assert put_body["spec"]["engine"]["resources"]["cpu"] == "2"
        assert put_body["spec"]["engine"]["resources"]["memory"] == "4Gi"
        assert put_body["spec"]["proxy"]["replicas"] == 3

    @pytest.mark.asyncio
    async def test_update_no_fields_keeps_current(self):
        client = EverestClient(base_url="http://fake:8080")
        client._token = "my-token"

        current = {
            "metadata": {"name": "my-db", "resourceVersion": "100"},
            "spec": {
                "engine": {
                    "type": "postgresql",
                    "replicas": 1,
                    "storage": {"size": "1Gi"},
                    "resources": {"cpu": "600m", "memory": "512Mi"},
                },
                "proxy": {"replicas": 1},
            },
        }

        get_resp = _mock_response(200, current)
        put_resp = _mock_response(200, current)

        mock_http = AsyncMock()
        mock_http.request.side_effect = [get_resp, put_resp]
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.everest_client.httpx.AsyncClient", return_value=mock_http):
            await client.update_database("my-db")

        # Spec should be unchanged
        put_body = mock_http.request.call_args_list[1].kwargs["json"]
        assert put_body["spec"]["engine"]["replicas"] == 1
        assert put_body["spec"]["engine"]["storage"]["size"] == "1Gi"


class TestGetDatabaseDetails:
    @pytest.mark.asyncio
    async def test_returns_structured_details(self):
        client = EverestClient(base_url="http://fake:8080")
        client._token = "my-token"

        mock_resp = _mock_response(
            200,
            {
                "metadata": {"name": "my-db", "resourceVersion": "100"},
                "spec": {
                    "engine": {
                        "type": "postgresql",
                        "version": "17.7",
                        "replicas": 1,
                        "storage": {"size": "1Gi"},
                        "resources": {"cpu": "600m", "memory": "512Mi"},
                    },
                },
                "status": {
                    "status": "ready",
                    "hostname": "my-db-pgbouncer.everest.svc",
                    "port": 5432,
                    "ready": 1,
                    "message": None,
                },
            },
        )
        mock_http = AsyncMock()
        mock_http.request.return_value = mock_resp
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.everest_client.httpx.AsyncClient", return_value=mock_http):
            details = await client.get_database_details("my-db")

        assert details["status"] == "ready"
        assert details["engine_version"] == "17.7"
        assert details["replicas"] == 1
        assert details["ready_replicas"] == 1
        assert details["storage"] == "1Gi"
        assert details["cpu"] == "600m"
        assert details["memory"] == "512Mi"
        assert details["hostname"] == "my-db-pgbouncer.everest.svc"
        assert details["port"] == 5432

    @pytest.mark.asyncio
    async def test_handles_missing_fields(self):
        client = EverestClient(base_url="http://fake:8080")
        client._token = "my-token"

        mock_resp = _mock_response(
            200,
            {
                "metadata": {"name": "my-db"},
                "spec": {"engine": {"type": "postgresql"}},
                "status": {"status": "initializing"},
            },
        )
        mock_http = AsyncMock()
        mock_http.request.return_value = mock_resp
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.everest_client.httpx.AsyncClient", return_value=mock_http):
            details = await client.get_database_details("my-db")

        assert details["status"] == "initializing"
        assert details["engine_version"] is None
        assert details["hostname"] is None


class TestListEngines:
    @pytest.mark.asyncio
    async def test_list_engines(self):
        client = EverestClient(base_url="http://fake:8080")
        client._token = "my-token"

        engines = [
            {"metadata": {"name": "percona-postgresql"}, "spec": {"type": "postgresql"}},
            {"metadata": {"name": "percona-xtradb"}, "spec": {"type": "pxc"}},
        ]
        mock_resp = _mock_response(200, {"items": engines})
        mock_http = AsyncMock()
        mock_http.request.return_value = mock_resp
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.everest_client.httpx.AsyncClient", return_value=mock_http):
            result = await client.list_engines()

        assert len(result) == 2
        assert result[0]["spec"]["type"] == "postgresql"
