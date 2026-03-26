import asyncio
import logging

from kubernetes import client as k8s_client_lib
from kubernetes.client.exceptions import ApiException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.k8s.client import K8sClient
from app.models.managed_service import ManagedService

logger = logging.getLogger(__name__)

# Default container port — apps should bind to PORT env var
_DEFAULT_APP_PORT = 8000


async def get_service_secret_names(db: AsyncSession, tenant_id: object) -> list[str]:
    """Return secret names of all ready/provisioning managed services for a tenant."""
    result = await db.execute(
        select(ManagedService.secret_name).where(
            ManagedService.tenant_id == tenant_id,
            ManagedService.secret_name.isnot(None),
        )
    )
    return [row[0] for row in result.all()]


class DeployService:
    """Creates/updates K8s Deployment + Service + HTTPRoute + HPA for tenant applications."""

    def __init__(self, k8s: K8sClient) -> None:
        self.k8s = k8s

    async def deploy(
        self,
        *,
        namespace: str,
        tenant_slug: str,
        app_slug: str,
        image: str,
        replicas: int,
        env_vars: dict[str, str],
        service_secret_names: list[str] | None = None,
        port: int = _DEFAULT_APP_PORT,
    ) -> None:
        """Create or update Deployment + Service + HTTPRoute + HPA."""
        logger.info("Deploying app: namespace=%s app=%s image=%s port=%d", namespace, app_slug, image, port)

        if not self.k8s.is_available() or self.k8s.apps_v1 is None:
            logger.warning("K8s unavailable — skipping deploy for %s/%s", namespace, app_slug)
            return

        await asyncio.gather(
            self._apply_deployment(
                namespace=namespace,
                app_slug=app_slug,
                image=image,
                replicas=replicas,
                env_vars=env_vars,
                service_secret_names=service_secret_names,
                port=port,
            ),
            self._apply_service(namespace=namespace, app_slug=app_slug, port=port),
        )

        # HTTPRoute and HPA after service exists
        await asyncio.gather(
            self._apply_httproute(
                namespace=namespace,
                tenant_slug=tenant_slug,
                app_slug=app_slug,
            ),
            self._apply_hpa(namespace=namespace, app_slug=app_slug),
        )

        logger.info("Deploy complete: namespace=%s app=%s", namespace, app_slug)

    async def wait_for_ready(self, namespace: str, app_slug: str, timeout: int = 120) -> tuple[bool, str]:
        """Wait for deployment to have at least 1 ready replica. Returns (success, message)."""
        for _ in range(timeout // 5):
            try:
                dep = await asyncio.to_thread(
                    self.k8s.apps_v1.read_namespaced_deployment_status,
                    name=app_slug,
                    namespace=namespace,
                )
                if dep.status.ready_replicas and dep.status.ready_replicas >= 1:
                    return True, "Deployment ready"

                # Check for pod errors that indicate permanent failure
                pods = await asyncio.to_thread(
                    self.k8s.core_v1.list_namespaced_pod,
                    namespace=namespace,
                    label_selector=f"app={app_slug}",
                )
                for pod in pods.items:
                    for cs in (pod.status.container_statuses or []):
                        if cs.state.waiting and cs.state.waiting.reason in (
                            "CrashLoopBackOff",
                            "ErrImagePull",
                            "ImagePullBackOff",
                        ):
                            return (
                                False,
                                f"Pod {pod.metadata.name}: {cs.state.waiting.reason}"
                                f" - {cs.state.waiting.message or ''}",
                            )
            except Exception:  # noqa: BLE001
                pass
            await asyncio.sleep(5)
        return False, f"Deployment not ready after {timeout}s"

    async def scale(self, *, namespace: str, app_slug: str, replicas: int) -> None:
        """Scale deployment replicas."""
        logger.info("Scaling: namespace=%s app=%s replicas=%d", namespace, app_slug, replicas)
        patch = {"spec": {"replicas": replicas}}
        await asyncio.to_thread(
            self.k8s.apps_v1.patch_namespaced_deployment_scale,
            name=app_slug,
            namespace=namespace,
            body=patch,
        )

    async def undeploy(self, *, namespace: str, app_slug: str) -> None:
        """Remove Deployment, Service, HTTPRoute, and HPA."""
        logger.info("Undeploying: namespace=%s app=%s", namespace, app_slug)
        delete_opts = k8s_client_lib.V1DeleteOptions(propagation_policy="Foreground")

        async def _delete_ignore_404(coro_factory):  # type: ignore[no-untyped-def]
            try:
                await coro_factory()
            except ApiException as e:
                if e.status != 404:
                    raise
                logger.debug("Resource already absent during undeploy: %s", e.reason)

        await asyncio.gather(
            _delete_ignore_404(
                lambda: asyncio.to_thread(
                    self.k8s.apps_v1.delete_namespaced_deployment,
                    name=app_slug,
                    namespace=namespace,
                    body=delete_opts,
                )
            ),
            _delete_ignore_404(
                lambda: asyncio.to_thread(
                    self.k8s.core_v1.delete_namespaced_service,
                    name=app_slug,
                    namespace=namespace,
                )
            ),
            _delete_ignore_404(
                lambda: asyncio.to_thread(
                    self.k8s.custom_objects.delete_namespaced_custom_object,
                    group="gateway.networking.k8s.io",
                    version="v1",
                    plural="httproutes",
                    namespace=namespace,
                    name=app_slug,
                )
            ),
            _delete_ignore_404(
                lambda: asyncio.to_thread(
                    self.k8s.autoscaling_v2.delete_namespaced_horizontal_pod_autoscaler,
                    name=app_slug,
                    namespace=namespace,
                )
            ),
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _apply_deployment(
        self,
        *,
        namespace: str,
        app_slug: str,
        image: str,
        replicas: int,
        env_vars: dict[str, str],
        service_secret_names: list[str] | None = None,
        port: int = _DEFAULT_APP_PORT,
    ) -> None:
        env_list = [k8s_client_lib.V1EnvVar(name="PORT", value=str(port))]
        env_list += [k8s_client_lib.V1EnvVar(name=k, value=v) for k, v in env_vars.items()]

        env_from = [
            k8s_client_lib.V1EnvFromSource(
                secret_ref=k8s_client_lib.V1SecretEnvSource(name=sn, optional=True)
            )
            for sn in (service_secret_names or [])
        ]

        deployment = k8s_client_lib.V1Deployment(
            api_version="apps/v1",
            kind="Deployment",
            metadata=k8s_client_lib.V1ObjectMeta(
                name=app_slug,
                namespace=namespace,
                labels={"app": app_slug, "haven/managed": "true"},
            ),
            spec=k8s_client_lib.V1DeploymentSpec(
                replicas=replicas,
                selector=k8s_client_lib.V1LabelSelector(match_labels={"app": app_slug}),
                template=k8s_client_lib.V1PodTemplateSpec(
                    metadata=k8s_client_lib.V1ObjectMeta(labels={"app": app_slug}),
                    spec=k8s_client_lib.V1PodSpec(
                        containers=[
                            k8s_client_lib.V1Container(
                                name=app_slug,
                                image=image,
                                image_pull_policy="Always",
                                ports=[
                                    k8s_client_lib.V1ContainerPort(container_port=port)
                                ],
                                env=env_list,
                                env_from=env_from,
                                resources=k8s_client_lib.V1ResourceRequirements(
                                    requests={"cpu": "50m", "memory": "64Mi"},
                                    limits={"cpu": "500m", "memory": "512Mi"},
                                ),
                                liveness_probe=k8s_client_lib.V1Probe(
                                    tcp_socket=k8s_client_lib.V1TCPSocketAction(
                                        port=port
                                    ),
                                    initial_delay_seconds=10,
                                    period_seconds=10,
                                ),
                            )
                        ],
                        tolerations=[k8s_client_lib.V1Toleration(operator="Exists")],
                        image_pull_secrets=[
                            k8s_client_lib.V1LocalObjectReference(
                                name=settings.harbor_registry_secret
                            )
                        ],
                    ),
                ),
            ),
        )

        await self._create_or_patch(
            read_fn=lambda: asyncio.to_thread(
                self.k8s.apps_v1.read_namespaced_deployment,
                name=app_slug,
                namespace=namespace,
            ),
            create_fn=lambda: asyncio.to_thread(
                self.k8s.apps_v1.create_namespaced_deployment,
                namespace=namespace,
                body=deployment,
            ),
            patch_fn=lambda: asyncio.to_thread(
                self.k8s.apps_v1.patch_namespaced_deployment,
                name=app_slug,
                namespace=namespace,
                body=deployment,
            ),
            resource=f"Deployment/{app_slug}",
        )

    async def _apply_service(self, *, namespace: str, app_slug: str, port: int = _DEFAULT_APP_PORT) -> None:
        service = k8s_client_lib.V1Service(
            api_version="v1",
            kind="Service",
            metadata=k8s_client_lib.V1ObjectMeta(
                name=app_slug,
                namespace=namespace,
                labels={"app": app_slug, "haven/managed": "true"},
            ),
            spec=k8s_client_lib.V1ServiceSpec(
                selector={"app": app_slug},
                ports=[
                    k8s_client_lib.V1ServicePort(
                        protocol="TCP",
                        port=80,
                        target_port=port,
                    )
                ],
                type="ClusterIP",
            ),
        )

        await self._create_or_patch(
            read_fn=lambda: asyncio.to_thread(
                self.k8s.core_v1.read_namespaced_service,
                name=app_slug,
                namespace=namespace,
            ),
            create_fn=lambda: asyncio.to_thread(
                self.k8s.core_v1.create_namespaced_service,
                namespace=namespace,
                body=service,
            ),
            patch_fn=lambda: asyncio.to_thread(
                self.k8s.core_v1.patch_namespaced_service,
                name=app_slug,
                namespace=namespace,
                body=service,
            ),
            resource=f"Service/{app_slug}",
        )

    async def _apply_httproute(
        self,
        *,
        namespace: str,
        tenant_slug: str,
        app_slug: str,
    ) -> None:
        hostname = f"{app_slug}.{tenant_slug}.apps.{settings.lb_ip}.sslip.io"
        httproute = {
            "apiVersion": "gateway.networking.k8s.io/v1",
            "kind": "HTTPRoute",
            "metadata": {
                "name": app_slug,
                "namespace": namespace,
                "labels": {"app": app_slug, "haven/managed": "true"},
            },
            "spec": {
                "parentRefs": [
                    {
                        "namespace": "haven-gateway",
                        "name": "haven-gateway",
                    }
                ],
                "hostnames": [hostname],
                "rules": [
                    {
                        "matches": [{"path": {"type": "PathPrefix", "value": "/"}}],
                        "backendRefs": [{"name": app_slug, "port": 80}],
                    }
                ],
            },
        }

        try:
            await self._create_or_patch_custom(
                group="gateway.networking.k8s.io",
                version="v1",
                plural="httproutes",
                namespace=namespace,
                name=app_slug,
                body=httproute,
            )
            logger.info("HTTPRoute applied: %s → %s", app_slug, hostname)
        except ApiException as e:
            # Gateway API CRD may not be installed (e.g. local dev)
            logger.warning("HTTPRoute skipped (CRD not available): %s", e.reason)

    async def _apply_hpa(self, *, namespace: str, app_slug: str) -> None:
        if self.k8s.autoscaling_v2 is None:
            logger.warning("autoscaling_v2 not available — skipping HPA for %s", app_slug)
            return

        hpa = k8s_client_lib.V2HorizontalPodAutoscaler(
            api_version="autoscaling/v2",
            kind="HorizontalPodAutoscaler",
            metadata=k8s_client_lib.V1ObjectMeta(
                name=app_slug,
                namespace=namespace,
                labels={"app": app_slug, "haven/managed": "true"},
            ),
            spec=k8s_client_lib.V2HorizontalPodAutoscalerSpec(
                scale_target_ref=k8s_client_lib.V2CrossVersionObjectReference(
                    api_version="apps/v1",
                    kind="Deployment",
                    name=app_slug,
                ),
                min_replicas=1,
                max_replicas=5,
                metrics=[
                    k8s_client_lib.V2MetricSpec(
                        type="Resource",
                        resource=k8s_client_lib.V2ResourceMetricSource(
                            name="cpu",
                            target=k8s_client_lib.V2MetricTarget(
                                type="Utilization",
                                average_utilization=70,
                            ),
                        ),
                    )
                ],
            ),
        )

        await self._create_or_patch(
            read_fn=lambda: asyncio.to_thread(
                self.k8s.autoscaling_v2.read_namespaced_horizontal_pod_autoscaler,
                name=app_slug,
                namespace=namespace,
            ),
            create_fn=lambda: asyncio.to_thread(
                self.k8s.autoscaling_v2.create_namespaced_horizontal_pod_autoscaler,
                namespace=namespace,
                body=hpa,
            ),
            patch_fn=lambda: asyncio.to_thread(
                self.k8s.autoscaling_v2.patch_namespaced_horizontal_pod_autoscaler,
                name=app_slug,
                namespace=namespace,
                body=hpa,
            ),
            resource=f"HPA/{app_slug}",
        )

    @staticmethod
    async def _create_or_patch(
        *,
        read_fn,  # type: ignore[type-arg]
        create_fn,  # type: ignore[type-arg]
        patch_fn,  # type: ignore[type-arg]
        resource: str,
    ) -> None:
        """Try to read; if 404 create, otherwise patch."""
        try:
            await read_fn()
            await patch_fn()
            logger.debug("Patched %s", resource)
        except ApiException as e:
            if e.status == 404:
                await create_fn()
                logger.debug("Created %s", resource)
            else:
                raise

    async def _create_or_patch_custom(
        self,
        *,
        group: str,
        version: str,
        plural: str,
        namespace: str,
        name: str,
        body: dict,  # type: ignore[type-arg]
    ) -> None:
        """Try to get custom object; if 404 create, otherwise replace."""
        try:
            await asyncio.to_thread(
                self.k8s.custom_objects.get_namespaced_custom_object,
                group=group,
                version=version,
                plural=plural,
                namespace=namespace,
                name=name,
            )
            await asyncio.to_thread(
                self.k8s.custom_objects.replace_namespaced_custom_object,
                group=group,
                version=version,
                plural=plural,
                namespace=namespace,
                name=name,
                body=body,
            )
            logger.debug("Replaced custom object %s/%s", plural, name)
        except ApiException as e:
            if e.status == 404:
                await asyncio.to_thread(
                    self.k8s.custom_objects.create_namespaced_custom_object,
                    group=group,
                    version=version,
                    plural=plural,
                    namespace=namespace,
                    body=body,
                )
                logger.debug("Created custom object %s/%s", plural, name)
            else:
                raise
