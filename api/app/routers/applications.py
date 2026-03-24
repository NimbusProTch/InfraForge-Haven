
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.deps import DBSession, K8sDep
from app.models.application import Application
from app.models.tenant import Tenant
from app.schemas.application import ApplicationCreate, ApplicationResponse, ApplicationUpdate

router = APIRouter(prefix="/tenants/{tenant_slug}/apps", tags=["applications"])


async def _get_tenant_or_404(tenant_slug: str, db: DBSession) -> Tenant:
    result = await db.execute(select(Tenant).where(Tenant.slug == tenant_slug))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


@router.get("", response_model=list[ApplicationResponse])
async def list_applications(tenant_slug: str, db: DBSession) -> list[Application]:
    tenant = await _get_tenant_or_404(tenant_slug, db)
    result = await db.execute(
        select(Application)
        .where(Application.tenant_id == tenant.id)
        .order_by(Application.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("", response_model=ApplicationResponse, status_code=status.HTTP_201_CREATED)
async def create_application(
    tenant_slug: str, body: ApplicationCreate, db: DBSession, k8s: K8sDep
) -> Application:
    tenant = await _get_tenant_or_404(tenant_slug, db)

    # Check slug uniqueness within tenant
    existing = await db.execute(
        select(Application).where(
            Application.tenant_id == tenant.id, Application.slug == body.slug
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail=f"Application '{body.slug}' already exists")

    app = Application(
        tenant_id=tenant.id,
        slug=body.slug,
        name=body.name,
        repo_url=body.repo_url,
        branch=body.branch,
        env_vars=body.env_vars,
        replicas=body.replicas,
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return app


@router.get("/{app_slug}", response_model=ApplicationResponse)
async def get_application(tenant_slug: str, app_slug: str, db: DBSession) -> Application:
    tenant = await _get_tenant_or_404(tenant_slug, db)
    result = await db.execute(
        select(Application).where(
            Application.tenant_id == tenant.id, Application.slug == app_slug
        )
    )
    app = result.scalar_one_or_none()
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return app


@router.patch("/{app_slug}", response_model=ApplicationResponse)
async def update_application(
    tenant_slug: str, app_slug: str, body: ApplicationUpdate, db: DBSession
) -> Application:
    tenant = await _get_tenant_or_404(tenant_slug, db)
    result = await db.execute(
        select(Application).where(
            Application.tenant_id == tenant.id, Application.slug == app_slug
        )
    )
    app = result.scalar_one_or_none()
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(app, field, value)

    await db.commit()
    await db.refresh(app)
    return app


@router.delete("/{app_slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_application(
    tenant_slug: str, app_slug: str, db: DBSession, k8s: K8sDep
) -> None:
    tenant = await _get_tenant_or_404(tenant_slug, db)
    result = await db.execute(
        select(Application).where(
            Application.tenant_id == tenant.id, Application.slug == app_slug
        )
    )
    app = result.scalar_one_or_none()
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")

    # TODO (Sprint 3): undeploy from K8s before deleting from DB
    await db.delete(app)
    await db.commit()
