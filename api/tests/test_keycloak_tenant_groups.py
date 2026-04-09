"""Tests for KeycloakService tenant group management (H1a-2 kubectl OIDC).

These methods land in the shared `haven` realm and are mirrored by the
`tenant_service.py::_create_rbac` RoleBindings against subjects like
`oidc:tenant_{slug}_admin`. The kube-apiserver --oidc-groups-claim=groups
+ --oidc-groups-prefix=oidc: setup translates the Keycloak group name
into the K8s subject. These tests pin the contract.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.keycloak_service import KeycloakService


@pytest.fixture
def kc_service() -> KeycloakService:
    """Fresh KeycloakService instance bound to a fake admin endpoint."""
    svc = KeycloakService()
    svc._base_url = "https://kc.example/auth"
    svc._admin_user = "admin"
    svc._admin_password = "secret"
    svc._client_id = "admin-cli"
    return svc


@pytest.fixture
def fake_token_patcher(kc_service):
    """Patch _get_admin_token to skip the real Keycloak login round-trip."""
    with patch.object(kc_service, "_get_admin_token", new=AsyncMock(return_value="fake-token")):
        yield


def _make_async_client_mock(responses: dict[tuple[str, str], httpx.Response]):
    """Build an httpx.AsyncClient mock whose method calls return canned responses.

    Keyed by (method.upper(), url-substring) → Response. URL match is substring.
    """

    def _build_matcher(method: str):
        async def _matcher(url: str, **kwargs) -> httpx.Response:
            for (m, sub), resp in responses.items():
                if m == method and sub in url:
                    return resp
            raise AssertionError(f"No mock match for {method} {url}")

        return _matcher

    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.get = AsyncMock(side_effect=_build_matcher("GET"))
    client.post = AsyncMock(side_effect=_build_matcher("POST"))
    client.put = AsyncMock(side_effect=_build_matcher("PUT"))
    client.delete = AsyncMock(side_effect=_build_matcher("DELETE"))
    return client


def _resp(status_code: int, json_body=None, headers=None):
    """Lightweight Response stub. We can't use httpx.Response directly because
    raise_for_status() requires a bound `_request`, which we'd have to fake.
    A MagicMock is enough — the production code only touches .status_code,
    .json(), .headers, .text, and .raise_for_status()."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json = MagicMock(return_value=json_body if json_body is not None else {})
    resp.headers = headers or {}
    resp.text = ""
    if 200 <= status_code < 400:
        resp.raise_for_status = MagicMock()
    else:
        resp.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                f"{status_code}",
                request=MagicMock(),
                response=resp,
            )
        )
    return resp


@pytest.mark.asyncio
async def test_create_tenant_groups_creates_three_groups(kc_service, fake_token_patcher):
    """All three role groups (admin, developer, viewer) are created."""
    # Each POST returns 201 with a Location header containing the new group ID
    responses = {
        ("POST", "/groups"): _resp(
            201,
            headers={"Location": "/admin/realms/haven/groups/grp-id-1"},
        ),
    }
    client_mock = _make_async_client_mock(responses)

    with patch("app.services.keycloak_service.httpx.AsyncClient", return_value=client_mock):
        result = await kc_service.create_tenant_groups("rotterdam")

    assert set(result.keys()) == {"admin", "developer", "viewer"}
    # 3 POST /groups calls (one per role)
    assert client_mock.post.call_count == 3
    # Each call carries the correct group name
    posted_names = [call.kwargs["json"]["name"] for call in client_mock.post.call_args_list]
    assert posted_names == [
        "tenant_rotterdam_admin",
        "tenant_rotterdam_developer",
        "tenant_rotterdam_viewer",
    ]


@pytest.mark.asyncio
async def test_create_tenant_groups_idempotent_on_409(kc_service, fake_token_patcher):
    """If a group already exists (409), the existing ID is fetched via search.

    Only the role whose name matches the search term gets resolved — the
    others fall through (logged warning). This test pins the contract that
    409 + search-by-name does not raise.
    """
    # POST 409 → GET search returns ONE existing group (admin only)
    existing = [{"id": "existing-grp-id", "name": "tenant_rotterdam_admin"}]
    responses = {
        ("POST", "/groups"): _resp(409),
        ("GET", "/groups"): _resp(200, json_body=existing),
    }
    client_mock = _make_async_client_mock(responses)

    with patch("app.services.keycloak_service.httpx.AsyncClient", return_value=client_mock):
        result = await kc_service.create_tenant_groups("rotterdam")

    # 3 POST attempts + 3 GET search fallbacks (one per role)
    assert client_mock.post.call_count == 3
    assert client_mock.get.call_count == 3
    # Only admin matches the search filter `name == group_name`. Developer
    # and viewer fall through (warning logged) — no exception raised.
    assert "admin" in result
    assert result["admin"] == "existing-grp-id"


@pytest.mark.asyncio
async def test_delete_tenant_groups_best_effort(kc_service, fake_token_patcher):
    """delete_tenant_groups walks the three roles, looks each up, then DELETEs.

    The fixture's `existing` list only matches the `admin` group name, so only
    one DELETE is sent — the other two roles fall through (debug log "not
    found, skipping"). This pins the best-effort contract.
    """
    existing = [{"id": "grp-1", "name": "tenant_rotterdam_admin"}]
    responses = {
        ("GET", "/groups"): _resp(200, json_body=existing),
        ("DELETE", "/groups/"): _resp(204),
    }
    client_mock = _make_async_client_mock(responses)

    with patch("app.services.keycloak_service.httpx.AsyncClient", return_value=client_mock):
        await kc_service.delete_tenant_groups("rotterdam")

    # 3 GETs (one per role) but only 1 DELETE (only admin matched).
    assert client_mock.get.call_count == 3
    assert client_mock.delete.call_count == 1


@pytest.mark.asyncio
async def test_delete_tenant_groups_skips_missing(kc_service, fake_token_patcher):
    """If a group cannot be found (search returns []), no DELETE is sent for it."""
    responses = {
        ("GET", "/groups"): _resp(200, json_body=[]),  # nothing matches
    }
    client_mock = _make_async_client_mock(responses)

    with patch("app.services.keycloak_service.httpx.AsyncClient", return_value=client_mock):
        await kc_service.delete_tenant_groups("rotterdam")

    # 3 GETs (one per role) but ZERO DELETEs (everything was missing)
    assert client_mock.get.call_count == 3
    assert client_mock.delete.call_count == 0


@pytest.mark.asyncio
async def test_add_user_to_tenant_group_uses_canonical_name(kc_service, fake_token_patcher):
    """add_user_to_tenant_group looks up the group by exact name + PUTs the user."""
    existing = [{"id": "grp-id-99", "name": "tenant_rotterdam_admin"}]
    responses = {
        ("GET", "/groups"): _resp(200, json_body=existing),
        ("PUT", "/users/"): _resp(204),
    }
    client_mock = _make_async_client_mock(responses)

    with patch("app.services.keycloak_service.httpx.AsyncClient", return_value=client_mock):
        ok = await kc_service.add_user_to_tenant_group(
            user_id="user-abc",
            tenant_slug="rotterdam",
            role="admin",
        )

    assert ok is True
    # The PUT URL must include both the user ID and the group ID
    put_url = client_mock.put.call_args.args[0]
    assert "/users/user-abc/groups/grp-id-99" in put_url


@pytest.mark.asyncio
async def test_add_user_to_tenant_group_rejects_unknown_role(kc_service):
    """Roles outside (admin, developer, viewer) are rejected without any HTTP call."""
    ok = await kc_service.add_user_to_tenant_group(
        user_id="user-abc",
        tenant_slug="rotterdam",
        role="superuser",  # not in _TENANT_ROLES
    )
    assert ok is False


@pytest.mark.asyncio
async def test_add_user_to_tenant_group_skips_empty_user_id(kc_service):
    """Empty user_id (Keycloak user not yet created) is a no-op, not an error."""
    ok = await kc_service.add_user_to_tenant_group(
        user_id="",
        tenant_slug="rotterdam",
        role="admin",
    )
    assert ok is False


def test_tenant_group_name_format(kc_service):
    """The group name format is locked: tenant_{slug}_{role}.

    This MUST match `tenant_service.py:395` which uses
    `name=f\"oidc:tenant_{{slug}}_admin\"` (etc) as the K8s RoleBinding subject.
    """
    assert kc_service._tenant_group_name("rotterdam", "admin") == "tenant_rotterdam_admin"
    assert kc_service._tenant_group_name("amsterdam", "developer") == "tenant_amsterdam_developer"
    assert kc_service._tenant_group_name("utrecht", "viewer") == "tenant_utrecht_viewer"
