import logging

from kubernetes import client as k8s_lib
from kubernetes.client.exceptions import ApiException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.k8s.client import K8sClient
from app.models.managed_service import ManagedService

logger = logging.getLogger(__name__)


async def _get_service_secret_names(db: AsyncSession, tenant_id: object) -> list[str]:
    """Return secret names of all ready/provisioning managed services for a tenant."""
    result = await db.execute(
        select(ManagedService.secret_name).where(
            ManagedService.tenant_id == tenant_id,
            ManagedService.secret_name.isnot(None),
        )
    )
    return [row[0] for row in result.all()]


class DeployService:
    """Creates/updates K8s Deployment + HTTPRoute for tenant applications. (Sprint 3 implementation)"""

    def __init__(self, k8s: K8sClient) -> None:
        self.k8s = k8s

    async def deploy(
        self,
        *,
        namespace: str,
        app_slug: str,
        image: str,
        replicas: int,
        env_vars: dict[str, str],
        service_secret_names: list[str] | None = None,
    ) -> None:
        """Create or update Deployment + Service + HTTPRoute."""
        logger.info("Deploy triggered: namespace=%s app=%s image=%s", namespace, app_slug, image)

        if not self.k8s.is_available() or self.k8s.apps_v1 is None:
            logger.warning("K8s unavailable — skipping deploy for %s/%s", namespace, app_slug)
            return

        env_list = [
            k8s_lib.V1EnvVar(name=k, value=v) for k, v in (env_vars or {}).items()
        ]

        # envFrom: inject managed service secrets as environment variables
        env_from = [
            k8s_lib.V1EnvFromSource(
                secret_ref=k8s_lib.V1SecretEnvSource(name=secret_name, optional=True)
            )
            for secret_name in (service_secret_names or [])
        ]

        container = k8s_lib.V1Container(
            name=app_slug,
            image=image,
            env=env_list,
            env_from=env_from,
            resources=k8s_lib.V1ResourceRequirements(
                requests={"cpu": "100m", "memory": "128Mi"},
                limits={"memory": "512Mi"},
            ),
        )

        pod_spec = k8s_lib.V1PodSpec(
            containers=[container],
            tolerations=[k8s_lib.V1Toleration(operator="Exists")],
        )

        deployment = k8s_lib.V1Deployment(
            metadata=k8s_lib.V1ObjectMeta(
                name=app_slug,
                namespace=namespace,
                labels={"app": app_slug, "haven.io/managed": "true"},
            ),
            spec=k8s_lib.V1DeploymentSpec(
                replicas=replicas,
                selector=k8s_lib.V1LabelSelector(match_labels={"app": app_slug}),
                template=k8s_lib.V1PodTemplateSpec(
                    metadata=k8s_lib.V1ObjectMeta(labels={"app": app_slug}),
                    spec=pod_spec,
                ),
            ),
        )

        try:
            self.k8s.apps_v1.create_namespaced_deployment(namespace, deployment)
        except ApiException as e:
            if e.status == 409:
                self.k8s.apps_v1.patch_namespaced_deployment(app_slug, namespace, deployment)
            else:
                raise

        logger.info("Deployment %s/%s applied", namespace, app_slug)

    async def scale(self, *, namespace: str, app_slug: str, replicas: int) -> None:
        """Scale deployment replicas. (skeleton)"""
        # TODO: apps_v1.patch_namespaced_deployment_scale
        logger.info("Scale: namespace=%s app=%s replicas=%d", namespace, app_slug, replicas)

    async def undeploy(self, *, namespace: str, app_slug: str) -> None:
        """Remove Deployment, Service, and HTTPRoute. (skeleton)"""
        logger.info("Undeploy: namespace=%s app=%s", namespace, app_slug)
