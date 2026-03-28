"""Unit tests for ManagedService Pydantic schemas."""

import pytest
from pydantic import ValidationError

from app.models.managed_service import ServiceTier, ServiceType
from app.schemas.managed_service import ManagedServiceCreate


class TestManagedServiceCreate:
    """Validate input schema for creating a managed service."""

    def test_valid_postgres(self):
        svc = ManagedServiceCreate(name="my-db", service_type=ServiceType.POSTGRES)
        assert svc.name == "my-db"
        assert svc.service_type == ServiceType.POSTGRES
        assert svc.tier == ServiceTier.DEV

    def test_valid_all_service_types(self):
        for stype in ServiceType:
            svc = ManagedServiceCreate(name="test-svc", service_type=stype)
            assert svc.service_type == stype

    def test_valid_tiers(self):
        for tier in ServiceTier:
            svc = ManagedServiceCreate(name="test-svc", service_type=ServiceType.REDIS, tier=tier)
            assert svc.tier == tier

    def test_name_too_short(self):
        with pytest.raises(ValidationError):
            ManagedServiceCreate(name="a", service_type=ServiceType.POSTGRES)

    def test_name_too_long(self):
        with pytest.raises(ValidationError):
            ManagedServiceCreate(name="a" * 64, service_type=ServiceType.POSTGRES)

    def test_name_starts_with_hyphen(self):
        with pytest.raises(ValidationError):
            ManagedServiceCreate(name="-mydb", service_type=ServiceType.POSTGRES)

    def test_name_ends_with_hyphen(self):
        with pytest.raises(ValidationError):
            ManagedServiceCreate(name="mydb-", service_type=ServiceType.POSTGRES)

    def test_name_uppercase_rejected(self):
        with pytest.raises(ValidationError):
            ManagedServiceCreate(name="MyDB", service_type=ServiceType.POSTGRES)

    def test_name_with_underscore_rejected(self):
        with pytest.raises(ValidationError):
            ManagedServiceCreate(name="my_db", service_type=ServiceType.POSTGRES)

    def test_reserved_name_default(self):
        with pytest.raises(ValidationError, match="reserved"):
            ManagedServiceCreate(name="default", service_type=ServiceType.POSTGRES)

    def test_reserved_name_admin(self):
        with pytest.raises(ValidationError, match="reserved"):
            ManagedServiceCreate(name="admin", service_type=ServiceType.POSTGRES)

    def test_reserved_name_system(self):
        with pytest.raises(ValidationError, match="reserved"):
            ManagedServiceCreate(name="system", service_type=ServiceType.POSTGRES)

    def test_name_exactly_2_chars(self):
        """Minimum valid name: 2 chars (start+end, pattern requires [a-z0-9] at both ends)."""
        svc = ManagedServiceCreate(name="ab", service_type=ServiceType.POSTGRES)
        assert svc.name == "ab"

    def test_name_exactly_63_chars(self):
        long_name = "a" + "b" * 61 + "c"  # 63 chars, valid
        svc = ManagedServiceCreate(name=long_name, service_type=ServiceType.POSTGRES)
        assert len(svc.name) == 63

    def test_invalid_service_type(self):
        with pytest.raises(ValidationError):
            ManagedServiceCreate(name="mydb", service_type="oracle")
