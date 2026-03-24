import asyncio
import logging
import uuid

from kubernetes import client as k8s_client_lib
from kubernetes.client.exceptions import ApiException

from app.config import settings
from app.k8s.client import K8sClient

logger = logging.getLogger(__name__)

# Max poll iterations (5s each) → 30 minutes build timeout
_MAX_POLL_ITERATIONS = 360


class BuildService:
    """Manages Kaniko build jobs in Kubernetes."""

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
        """Submit a Kaniko Job and return the K8s job name."""
        job_name = f"build-{app_slug}-{commit_sha[:8]}-{uuid.uuid4().hex[:6]}"
        logger.info(
            "Submitting build job: job=%s repo=%s branch=%s commit=%s image=%s",
            job_name,
            repo_url,
            branch,
            commit_sha,
            image_name,
        )

        job_body = self._build_job_manifest(
            job_name=job_name,
            namespace=namespace,
            app_slug=app_slug,
            repo_url=repo_url,
            branch=branch,
            commit_sha=commit_sha,
            image_name=image_name,
        )

        await asyncio.to_thread(
            self.k8s.batch_v1.create_namespaced_job,
            namespace=namespace,
            body=job_body,
        )
        logger.info("Build job created: %s/%s", namespace, job_name)
        return job_name

    async def get_build_status(self, namespace: str, job_name: str) -> str:
        """Return current K8s job phase: pending | running | succeeded | failed."""
        try:
            job = await asyncio.to_thread(
                self.k8s.batch_v1.read_namespaced_job_status,
                name=job_name,
                namespace=namespace,
            )
            status = job.status
            if status.succeeded and status.succeeded >= 1:
                return "succeeded"
            if status.failed and status.failed >= 1:
                backoff = job.spec.backoff_limit if job.spec.backoff_limit is not None else 6
                if status.failed > backoff:
                    return "failed"
            if status.active and status.active >= 1:
                return "running"
            return "pending"
        except ApiException as e:
            if e.status == 404:
                return "not_found"
            raise

    async def wait_for_completion(self, namespace: str, job_name: str) -> str:
        """Poll job status until succeeded/failed. Returns final status string."""
        for _ in range(_MAX_POLL_ITERATIONS):
            status = await self.get_build_status(namespace, job_name)
            logger.debug("Build job %s status: %s", job_name, status)
            if status in ("succeeded", "failed", "not_found"):
                return status
            await asyncio.sleep(5)
        logger.error("Build job %s timed out after %d polls", job_name, _MAX_POLL_ITERATIONS)
        return "failed"

    async def get_build_logs(self, namespace: str, job_name: str) -> str:
        """Fetch logs from the kaniko pod for this job."""
        try:
            pods = await asyncio.to_thread(
                self.k8s.core_v1.list_namespaced_pod,
                namespace=namespace,
                label_selector=f"job-name={job_name}",
            )
            if not pods.items:
                return ""
            pod_name = pods.items[0].metadata.name
            logs: str = await asyncio.to_thread(
                self.k8s.core_v1.read_namespaced_pod_log,
                name=pod_name,
                namespace=namespace,
                container="kaniko",
                tail_lines=500,
            )
            return logs
        except ApiException as e:
            logger.warning("Failed to get build logs for %s: %s", job_name, e)
            return ""

    def _build_job_manifest(
        self,
        *,
        job_name: str,
        namespace: str,
        app_slug: str,
        repo_url: str,
        branch: str,
        commit_sha: str,
        image_name: str,
    ) -> k8s_client_lib.V1Job:
        """Construct the K8s Job manifest for the build pipeline.

        Pipeline:
          initContainer git-clone  → alpine/git: clone repo + checkout commit
          initContainer nixpacks   → ghcr.io/railwayapp/nixpacks: generate Dockerfile
          container     kaniko     → gcr.io/kaniko-project/executor: build + push to Harbor
        """
        git_clone_cmd = (
            f"git clone --depth=50 '{repo_url}' /workspace "
            f"&& cd /workspace "
            f"&& git checkout '{commit_sha}'"
        )
        nixpacks_cmd = (
            "if [ ! -f /workspace/Dockerfile ]; then "
            "  /usr/local/bin/nixpacks build /workspace --out /workspace "
            "  && cp /workspace/.nixpacks/Dockerfile /workspace/Dockerfile; "
            "fi"
        )

        init_containers = [
            k8s_client_lib.V1Container(
                name="git-clone",
                image="alpine/git:latest",
                command=["sh", "-c"],
                args=[git_clone_cmd],
                volume_mounts=[
                    k8s_client_lib.V1VolumeMount(name="workspace", mount_path="/workspace")
                ],
            ),
            k8s_client_lib.V1Container(
                name="nixpacks",
                image="ghcr.io/railwayapp/nixpacks:latest",
                command=["/bin/sh", "-c"],
                args=[nixpacks_cmd],
                volume_mounts=[
                    k8s_client_lib.V1VolumeMount(name="workspace", mount_path="/workspace")
                ],
            ),
        ]

        kaniko_container = k8s_client_lib.V1Container(
            name="kaniko",
            image="gcr.io/kaniko-project/executor:latest",
            args=[
                "--context=dir:///workspace",
                "--dockerfile=/workspace/Dockerfile",
                f"--destination={image_name}",
                "--skip-tls-verify",
                "--cache=true",
                f"--cache-repo={settings.harbor_url}/{settings.harbor_project}/cache",
            ],
            volume_mounts=[
                k8s_client_lib.V1VolumeMount(name="workspace", mount_path="/workspace"),
                k8s_client_lib.V1VolumeMount(
                    name="kaniko-secret", mount_path="/kaniko/.docker"
                ),
            ],
        )

        volumes = [
            k8s_client_lib.V1Volume(
                name="workspace", empty_dir=k8s_client_lib.V1EmptyDirVolumeSource()
            ),
            k8s_client_lib.V1Volume(
                name="kaniko-secret",
                secret=k8s_client_lib.V1SecretVolumeSource(
                    secret_name=settings.harbor_registry_secret,
                    items=[
                        k8s_client_lib.V1KeyToPath(
                            key=".dockerconfigjson", path="config.json"
                        )
                    ],
                ),
            ),
        ]

        pod_spec = k8s_client_lib.V1PodSpec(
            restart_policy="Never",
            init_containers=init_containers,
            containers=[kaniko_container],
            volumes=volumes,
        )

        job_spec = k8s_client_lib.V1JobSpec(
            ttl_seconds_after_finished=3600,
            backoff_limit=1,
            template=k8s_client_lib.V1PodTemplateSpec(
                metadata=k8s_client_lib.V1ObjectMeta(
                    labels={"app": "haven-build", "job-name": job_name}
                ),
                spec=pod_spec,
            ),
        )

        return k8s_client_lib.V1Job(
            api_version="batch/v1",
            kind="Job",
            metadata=k8s_client_lib.V1ObjectMeta(
                name=job_name,
                namespace=namespace,
                labels={"haven/managed": "true", "haven/app": app_slug},
            ),
            spec=job_spec,
        )
