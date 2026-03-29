"""Unit tests for SecretService and EnvVar schema."""

import base64
from unittest.mock import MagicMock

import pytest
from kubernetes.client.exceptions import ApiException

from app.schemas.env_var import EnvVar, EnvVarList
from app.services.secret_service import SecretService, _secret_name

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_k8s_available() -> MagicMock:
    k8s = MagicMock()
    k8s.is_available.return_value = True
    k8s.core_v1 = MagicMock()
    return k8s


def _make_k8s_unavailable() -> MagicMock:
    k8s = MagicMock()
    k8s.is_available.return_value = False
    k8s.core_v1 = None
    return k8s


# ---------------------------------------------------------------------------
# EnvVar schema
# ---------------------------------------------------------------------------


class TestEnvVarSchema:
    def test_valid_key(self):
        v = EnvVar(key="DATABASE_URL", value="postgres://localhost/db")
        assert v.key == "DATABASE_URL"
        assert v.sensitive is False

    def test_sensitive_flag(self):
        v = EnvVar(key="API_KEY", value="secret123", sensitive=True)
        assert v.sensitive is True

    def test_key_must_match_identifier(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            EnvVar(key="123BAD", value="x")

    def test_key_with_leading_underscore(self):
        v = EnvVar(key="_MY_VAR", value="val")
        assert v.key == "_MY_VAR"

    def test_env_var_list_plaintext(self):
        lst = EnvVarList(
            vars=[
                EnvVar(key="PORT", value="8000"),
                EnvVar(key="SECRET", value="s3cr3t", sensitive=True),
            ]
        )
        plain = lst.plaintext()
        assert plain == {"PORT": "8000"}

    def test_env_var_list_sensitive(self):
        lst = EnvVarList(
            vars=[
                EnvVar(key="PORT", value="8000"),
                EnvVar(key="SECRET", value="s3cr3t", sensitive=True),
                EnvVar(key="TOKEN", value="tok", sensitive=True),
            ]
        )
        sens = lst.sensitive()
        assert sens == {"SECRET": "s3cr3t", "TOKEN": "tok"}

    def test_env_var_list_empty(self):
        lst = EnvVarList()
        assert lst.plaintext() == {}
        assert lst.sensitive() == {}


# ---------------------------------------------------------------------------
# _secret_name helper
# ---------------------------------------------------------------------------


class TestSecretName:
    def test_standard_slug(self):
        assert _secret_name("my-api") == "my-api-env-secrets"

    def test_simple_slug(self):
        assert _secret_name("backend") == "backend-env-secrets"


# ---------------------------------------------------------------------------
# SecretService.create_secret
# ---------------------------------------------------------------------------


class TestCreateSecret:
    def test_create_calls_k8s(self):
        k8s = _make_k8s_available()
        svc = SecretService(k8s)
        result = svc.create_secret("tenant-acme", "my-api", {"DB_URL": "postgres://..."})
        assert result is True
        k8s.core_v1.create_namespaced_secret.assert_called_once()
        call_kwargs = k8s.core_v1.create_namespaced_secret.call_args
        assert call_kwargs.kwargs["namespace"] == "tenant-acme"
        body = call_kwargs.kwargs["body"]
        assert body["metadata"]["name"] == "my-api-env-secrets"
        assert body["stringData"]["DB_URL"] == "postgres://..."

    def test_create_returns_false_when_k8s_unavailable(self):
        k8s = _make_k8s_unavailable()
        svc = SecretService(k8s)
        result = svc.create_secret("tenant-acme", "my-api", {"KEY": "val"})
        assert result is False

    def test_create_secret_labels(self):
        k8s = _make_k8s_available()
        svc = SecretService(k8s)
        svc.create_secret("tenant-x", "my-app", {"X": "y"})
        body = k8s.core_v1.create_namespaced_secret.call_args.kwargs["body"]
        labels = body["metadata"]["labels"]
        assert labels["app.kubernetes.io/managed-by"] == "haven"
        assert labels["haven.io/app"] == "my-app"
        assert labels["haven.io/secret-type"] == "env-vars"


# ---------------------------------------------------------------------------
# SecretService.upsert_secret
# ---------------------------------------------------------------------------


class TestUpsertSecret:
    def test_upsert_creates_when_not_exists(self):
        k8s = _make_k8s_available()
        svc = SecretService(k8s)
        result = svc.upsert_secret("tenant-acme", "my-api", {"KEY": "val"})
        assert result is True
        k8s.core_v1.create_namespaced_secret.assert_called_once()

    def test_upsert_replaces_on_conflict(self):
        k8s = _make_k8s_available()
        k8s.core_v1.create_namespaced_secret.side_effect = ApiException(status=409, reason="AlreadyExists")
        svc = SecretService(k8s)
        result = svc.upsert_secret("tenant-acme", "my-api", {"KEY": "val"})
        assert result is True
        k8s.core_v1.replace_namespaced_secret.assert_called_once()

    def test_upsert_returns_false_when_k8s_unavailable(self):
        k8s = _make_k8s_unavailable()
        svc = SecretService(k8s)
        result = svc.upsert_secret("tenant-acme", "my-api", {"KEY": "val"})
        assert result is False


# ---------------------------------------------------------------------------
# SecretService.delete_secret
# ---------------------------------------------------------------------------


class TestDeleteSecret:
    def test_delete_calls_k8s(self):
        k8s = _make_k8s_available()
        svc = SecretService(k8s)
        result = svc.delete_secret("tenant-acme", "my-api")
        assert result is True
        k8s.core_v1.delete_namespaced_secret.assert_called_once_with(
            name="my-api-env-secrets",
            namespace="tenant-acme",
        )

    def test_delete_404_is_idempotent(self):
        k8s = _make_k8s_available()
        k8s.core_v1.delete_namespaced_secret.side_effect = ApiException(status=404, reason="Not Found")
        svc = SecretService(k8s)
        result = svc.delete_secret("tenant-acme", "my-api")
        assert result is True  # idempotent — not an error

    def test_delete_returns_false_when_k8s_unavailable(self):
        k8s = _make_k8s_unavailable()
        svc = SecretService(k8s)
        result = svc.delete_secret("tenant-acme", "my-api")
        assert result is False

    def test_delete_reraises_non_404(self):
        k8s = _make_k8s_available()
        k8s.core_v1.delete_namespaced_secret.side_effect = ApiException(status=500, reason="Internal Error")
        svc = SecretService(k8s)
        with pytest.raises(ApiException):
            svc.delete_secret("tenant-acme", "my-api")


# ---------------------------------------------------------------------------
# SecretService.list_secret_keys
# ---------------------------------------------------------------------------


class TestListSecretKeys:
    def test_returns_keys_without_values(self):
        k8s = _make_k8s_available()
        mock_secret = MagicMock()
        mock_secret.data = {
            "DB_URL": base64.b64encode(b"postgres://...").decode(),
            "API_KEY": base64.b64encode(b"secret").decode(),
        }
        k8s.core_v1.read_namespaced_secret.return_value = mock_secret
        svc = SecretService(k8s)
        keys = svc.list_secret_keys("tenant-acme", "my-api")
        assert set(keys) == {"DB_URL", "API_KEY"}

    def test_returns_empty_list_when_secret_not_found(self):
        k8s = _make_k8s_available()
        k8s.core_v1.read_namespaced_secret.side_effect = ApiException(status=404, reason="Not Found")
        svc = SecretService(k8s)
        keys = svc.list_secret_keys("tenant-acme", "my-api")
        assert keys == []

    def test_returns_empty_list_when_k8s_unavailable(self):
        k8s = _make_k8s_unavailable()
        svc = SecretService(k8s)
        keys = svc.list_secret_keys("tenant-acme", "my-api")
        assert keys == []

    def test_returns_empty_list_when_data_is_none(self):
        k8s = _make_k8s_available()
        mock_secret = MagicMock()
        mock_secret.data = None
        k8s.core_v1.read_namespaced_secret.return_value = mock_secret
        svc = SecretService(k8s)
        keys = svc.list_secret_keys("tenant-acme", "my-api")
        assert keys == []


# ---------------------------------------------------------------------------
# SecretService.decode_secret_data
# ---------------------------------------------------------------------------


class TestDecodeSecretData:
    def test_decodes_base64_values(self):
        k8s = _make_k8s_available()
        svc = SecretService(k8s)
        encoded = {
            "DB_URL": base64.b64encode(b"postgres://localhost/db").decode(),
            "TOKEN": base64.b64encode(b"abc123").decode(),
        }
        decoded = svc.decode_secret_data(encoded)
        assert decoded == {"DB_URL": "postgres://localhost/db", "TOKEN": "abc123"}

    def test_empty_input(self):
        k8s = _make_k8s_available()
        svc = SecretService(k8s)
        assert svc.decode_secret_data({}) == {}


# ---------------------------------------------------------------------------
# SecretService.secret_name_for
# ---------------------------------------------------------------------------


class TestSecretNameFor:
    def test_returns_correct_name(self):
        k8s = _make_k8s_available()
        svc = SecretService(k8s)
        assert svc.secret_name_for("api-backend") == "api-backend-env-secrets"
