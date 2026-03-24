import logging
import uuid

from app.k8s.client import K8sClient

logger = logging.getLogger(__name__)


class BuildService:
    """Manages Kaniko build jobs in Kubernetes. (Sprint 3 implementation)"""

    def __init__(self, k8s: K8sClient) -> None:
        self.k8s = k8s

    async def trigger_build(
        self,
        *,
        namespace: str,
        app_slug: str,
        repo_url: str,
        branch: str,
        commit_sha: str,
        image_name: str,
    ) -> str:
        """Submit a Kaniko job and return the K8s job name. (skeleton)"""
        job_name = f"build-{app_slug}-{commit_sha[:8]}-{uuid.uuid4().hex[:6]}"
        logger.info(
            "Build triggered: job=%s repo=%s branch=%s commit=%s",
            job_name,
            repo_url,
            branch,
            commit_sha,
        )
        # TODO: Create k8s batch/v1 Job with Kaniko container
        # - Mount repo via git-clone init container
        # - Push to Harbor registry: {settings.harbor_url}/{namespace}/{app_slug}:{commit_sha}
        # - Report status back via deployment status update
        return job_name

    async def get_build_status(self, namespace: str, job_name: str) -> str:
        """Return current K8s job phase. (skeleton)"""
        # TODO: query batch_v1.read_namespaced_job_status and map to DeploymentStatus
        return "pending"

    async def get_build_logs(self, namespace: str, job_name: str) -> str:
        """Stream Kaniko pod logs. (skeleton)"""
        # TODO: core_v1.read_namespaced_pod_log with follow=False
        return ""
