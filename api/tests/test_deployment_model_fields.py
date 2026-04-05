"""Tests for Deployment model fields and DeploymentStatus enum.

Covers:
  - gitops_commit_sha field exists and can be set
  - status field has correct enum values
  - DeploymentStatus enum includes all expected statuses
  - Deployment model round-trip through database
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.deployment import Deployment, DeploymentStatus
from app.models.tenant import Tenant


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


async def _make_tenant_and_app(db: AsyncSession) -> tuple[Tenant, Application]:
    """Create a tenant and application for deployment tests."""
    tenant = Tenant(
        id=uuid.uuid4(),
        slug="deploy-model-test",
        name="Deploy Model Test",
        namespace="tenant-deploy-model-test",
        keycloak_realm="deploy-model-test",
        cpu_limit="4",
        memory_limit="8Gi",
        storage_limit="50Gi",
    )
    db.add(tenant)
    await db.flush()

    app_obj = Application(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        slug="model-app",
        name="Model App",
        repo_url="https://github.com/test/repo",
        branch="main",
    )
    db.add(app_obj)
    await db.commit()
    await db.refresh(tenant)
    await db.refresh(app_obj)
    return tenant, app_obj


# ---------------------------------------------------------------------------
# DeploymentStatus enum tests
# ---------------------------------------------------------------------------


class TestDeploymentStatusEnum:
    """Tests for DeploymentStatus enum values."""

    def test_enum_has_pending(self):
        assert DeploymentStatus.PENDING.value == "pending"

    def test_enum_has_building(self):
        assert DeploymentStatus.BUILDING.value == "building"

    def test_enum_has_deploying(self):
        assert DeploymentStatus.DEPLOYING.value == "deploying"

    def test_enum_has_running(self):
        assert DeploymentStatus.RUNNING.value == "running"

    def test_enum_has_failed(self):
        assert DeploymentStatus.FAILED.value == "failed"

    def test_enum_has_all_expected_values(self):
        expected = {"pending", "building", "built", "deploying", "running", "failed"}
        actual = {s.value for s in DeploymentStatus}
        assert expected == actual

    def test_enum_is_string_enum(self):
        """DeploymentStatus values should be strings (StrEnum)."""
        for status in DeploymentStatus:
            assert isinstance(status.value, str)
            # StrEnum members should be usable as strings
            assert str(status) == status.value


# ---------------------------------------------------------------------------
# Deployment model field tests
# ---------------------------------------------------------------------------


class TestDeploymentModelFields:
    """Tests for Deployment model fields including gitops_commit_sha."""

    @pytest.mark.asyncio
    async def test_gitops_commit_sha_field_exists(self, db_session: AsyncSession):
        """gitops_commit_sha field should exist and accept a string value."""
        _, app_obj = await _make_tenant_and_app(db_session)

        deployment = Deployment(
            id=uuid.uuid4(),
            application_id=app_obj.id,
            commit_sha="abc1234567890abcdef1234567890abcdef12345",
            status=DeploymentStatus.RUNNING,
            gitops_commit_sha="def456789",
        )
        db_session.add(deployment)
        await db_session.commit()
        await db_session.refresh(deployment)

        assert deployment.gitops_commit_sha == "def456789"

    @pytest.mark.asyncio
    async def test_gitops_commit_sha_nullable(self, db_session: AsyncSession):
        """gitops_commit_sha should be nullable (None by default)."""
        _, app_obj = await _make_tenant_and_app(db_session)

        deployment = Deployment(
            id=uuid.uuid4(),
            application_id=app_obj.id,
            commit_sha="abc1234567890abcdef1234567890abcdef12345",
            status=DeploymentStatus.PENDING,
        )
        db_session.add(deployment)
        await db_session.commit()
        await db_session.refresh(deployment)

        assert deployment.gitops_commit_sha is None

    @pytest.mark.asyncio
    async def test_status_default_is_pending(self, db_session: AsyncSession):
        """Default status should be PENDING."""
        _, app_obj = await _make_tenant_and_app(db_session)

        deployment = Deployment(
            id=uuid.uuid4(),
            application_id=app_obj.id,
            commit_sha="abc123",
        )
        db_session.add(deployment)
        await db_session.commit()
        await db_session.refresh(deployment)

        assert deployment.status == DeploymentStatus.PENDING

    @pytest.mark.asyncio
    async def test_all_status_values_persist(self, db_session: AsyncSession):
        """Each DeploymentStatus value should be persistable to the database."""
        _, app_obj = await _make_tenant_and_app(db_session)

        for status_val in DeploymentStatus:
            dep = Deployment(
                id=uuid.uuid4(),
                application_id=app_obj.id,
                commit_sha=f"sha-{status_val.value}",
                status=status_val,
            )
            db_session.add(dep)

        await db_session.commit()

    @pytest.mark.asyncio
    async def test_error_message_field(self, db_session: AsyncSession):
        """error_message should be settable and nullable."""
        _, app_obj = await _make_tenant_and_app(db_session)

        deployment = Deployment(
            id=uuid.uuid4(),
            application_id=app_obj.id,
            commit_sha="abc123",
            status=DeploymentStatus.FAILED,
            error_message="Pod CrashLoopBackOff: exit code 1",
        )
        db_session.add(deployment)
        await db_session.commit()
        await db_session.refresh(deployment)

        assert deployment.error_message == "Pod CrashLoopBackOff: exit code 1"

    @pytest.mark.asyncio
    async def test_build_job_name_and_image_tag(self, db_session: AsyncSession):
        """build_job_name and image_tag fields should persist correctly."""
        _, app_obj = await _make_tenant_and_app(db_session)

        deployment = Deployment(
            id=uuid.uuid4(),
            application_id=app_obj.id,
            commit_sha="abc123",
            status=DeploymentStatus.BUILDING,
            build_job_name="build-my-app-abc12345",
            image_tag="harbor.example.io/library/tenant-test/my-app:abc12345",
        )
        db_session.add(deployment)
        await db_session.commit()
        await db_session.refresh(deployment)

        assert deployment.build_job_name == "build-my-app-abc12345"
        assert deployment.image_tag == "harbor.example.io/library/tenant-test/my-app:abc12345"
