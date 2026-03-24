import logging

from kubernetes import client as k8s_client_lib
from kubernetes import config as k8s_config

from app.config import settings

logger = logging.getLogger(__name__)


class K8sClient:
    """Kubernetes API client wrapper."""

    def __init__(self) -> None:
        self._initialized = False
        self.core_v1: k8s_client_lib.CoreV1Api | None = None
        self.apps_v1: k8s_client_lib.AppsV1Api | None = None
        self.batch_v1: k8s_client_lib.BatchV1Api | None = None
        self.rbac_v1: k8s_client_lib.RbacAuthorizationV1Api | None = None
        self.autoscaling_v2: k8s_client_lib.AutoscalingV2Api | None = None
        self.custom_objects: k8s_client_lib.CustomObjectsApi | None = None

    async def initialize(self) -> None:
        try:
            if settings.k8s_incluster:
                k8s_config.load_incluster_config()
                logger.info("Loaded in-cluster Kubernetes config")
            else:
                k8s_config.load_kube_config(config_file=settings.k8s_kubeconfig)
                logger.info("Loaded kubeconfig")

            self.core_v1 = k8s_client_lib.CoreV1Api()
            self.apps_v1 = k8s_client_lib.AppsV1Api()
            self.batch_v1 = k8s_client_lib.BatchV1Api()
            self.rbac_v1 = k8s_client_lib.RbacAuthorizationV1Api()
            self.autoscaling_v2 = k8s_client_lib.AutoscalingV2Api()
            self.custom_objects = k8s_client_lib.CustomObjectsApi()
            self._initialized = True
        except Exception as e:
            logger.warning("Failed to initialize Kubernetes client: %s", e)
            # Allow startup without K8s (e.g., local dev without cluster)
            self._initialized = False

    async def close(self) -> None:
        self._initialized = False

    def is_available(self) -> bool:
        return self._initialized

    async def health_check(self) -> dict:
        if not self._initialized or self.core_v1 is None:
            return {"status": "unavailable", "error": "K8s client not initialized"}
        try:
            self.core_v1.get_api_resources()
            return {"status": "ok"}
        except Exception as e:
            return {"status": "error", "error": str(e)}


k8s_client = K8sClient()
