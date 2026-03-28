import asyncio
import logging
import uuid

from kubernetes import client as k8s_client_lib
from kubernetes.client.exceptions import ApiException

from app.k8s.client import K8sClient

logger = logging.getLogger(__name__)

# Max poll iterations (5s each) → 30 minutes build timeout
_MAX_POLL_ITERATIONS = 360


class BuildService:
    """Manages BuildKit-based build jobs in Kubernetes."""

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
        github_token: str | None = None,
    ) -> str:
        """Submit a BuildKit build Job and return the K8s job name."""
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
            github_token=github_token,
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
        """Fetch logs from all containers (init + main) for this build job."""
        try:
            pods = await asyncio.to_thread(
                self.k8s.core_v1.list_namespaced_pod,
                namespace=namespace,
                label_selector=f"job-name={job_name}",
            )
            if not pods.items:
                return ""
            pod = pods.items[0]
            pod_name = pod.metadata.name

            # Collect logs from init containers and main container
            containers = ["git-clone", "nixpacks", "buildctl"]
            all_logs: list[str] = []

            for container_name in containers:
                try:
                    log: str = await asyncio.to_thread(
                        self.k8s.core_v1.read_namespaced_pod_log,
                        name=pod_name,
                        namespace=namespace,
                        container=container_name,
                        tail_lines=200,
                    )
                    if log and log.strip():
                        all_logs.append(f"--- {container_name} ---\n{log}")
                except ApiException:
                    # Container may not have started (e.g. earlier init failed)
                    pass

            # Include pod status info to identify which container failed
            if pod.status and pod.status.init_container_statuses:
                for cs in pod.status.init_container_statuses:
                    if cs.state and cs.state.terminated and cs.state.terminated.exit_code != 0:
                        all_logs.insert(
                            0,
                            f"[init container '{cs.name}' failed with exit code {cs.state.terminated.exit_code}]",
                        )

            return "\n\n".join(all_logs)
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
        github_token: str | None = None,
    ) -> k8s_client_lib.V1Job:
        """Construct the K8s Job manifest for the build pipeline.

        Pipeline:
          initContainer git-clone  → alpine/git: clone repo + checkout commit
          initContainer nixpacks   → alpine: detect and generate Dockerfile if needed
          container     buildctl   → moby/buildkit: build + push via BuildKit daemon
        """
        # Inject auth into clone URL for private repos (do not modify stored repo_url)
        clone_url = repo_url
        if github_token and repo_url.startswith("https://"):
            clone_url = repo_url.replace("https://", f"https://oauth2:{github_token}@")

        _is_real_sha = len(commit_sha) >= 7 and all(c in "0123456789abcdef" for c in commit_sha)
        if _is_real_sha:
            git_clone_cmd = (
                f"git clone --depth=50 '{clone_url}' /workspace "
                f"&& cd /workspace "
                f"&& git checkout '{commit_sha}'"
            )
        else:
            git_clone_cmd = f"git clone --depth=1 --branch '{branch}' '{clone_url}' /workspace"
        # Download nixpacks CLI from GitHub releases and generate Dockerfile if missing.
        # Detect architecture to download correct binary (x86_64 vs aarch64).
        # If nixpacks fails (e.g. "No start command found"), auto-detect the start
        # command for common languages (Python, Node.js, Go) and retry.  When even
        # the retry fails, fall back to a simple generated Dockerfile.
        nixpacks_cmd = (
            "if [ ! -f /workspace/Dockerfile ]; then "
            "  apk add --no-cache curl tar grep && "
            "  NIXPACKS_VERSION=1.41.0 && "
            '  ARCH=$(uname -m) && '
            '  case "$ARCH" in aarch64|arm64) NIXARCH="aarch64" ;; *) NIXARCH="x86_64" ;; esac && '
            "  curl -fsSL -o /tmp/nixpacks.tar.gz "
            "    https://github.com/railwayapp/nixpacks/releases/download/v${NIXPACKS_VERSION}/"
            "nixpacks-v${NIXPACKS_VERSION}-${NIXARCH}-unknown-linux-musl.tar.gz && "
            "  tar -xzf /tmp/nixpacks.tar.gz -C /tmp && "
            "  chmod +x /tmp/nixpacks && "
            # --- First attempt: plain nixpacks build ---
            "  if /tmp/nixpacks build /workspace --out /workspace; then "
            "    cp /workspace/.nixpacks/Dockerfile /workspace/Dockerfile && "
            "    sed -i 's/uv==$NIXPACKS_UV_VERSION/uv/g' /workspace/Dockerfile; "
            "  else "
            # --- Detect start command for common languages ---
            '    echo "nixpacks failed, attempting start-command detection..." && '
            "    START_CMD= && "
            # Python detection
            "    if [ -f /workspace/requirements.txt ] || [ -f /workspace/pyproject.toml ] || [ -f /workspace/setup.py ]; then "  # noqa: E501
            "      if [ -f /workspace/main.py ]; then "
            '        START_CMD="python main.py"; '
            "      elif [ -f /workspace/app.py ]; then "
            '        START_CMD="python app.py"; '
            "      elif [ -f /workspace/manage.py ]; then "
            '        START_CMD="python manage.py runserver 0.0.0.0:8000"; '
            "      elif [ -f /workspace/wsgi.py ]; then "
            '        START_CMD="gunicorn wsgi:application --bind 0.0.0.0:8000"; '
            "      elif grep -q -i 'uvicorn\\|fastapi' /workspace/requirements.txt 2>/dev/null; then "
            '        APP_MODULE=$(grep -rl "FastAPI()" /workspace --include="*.py" 2>/dev/null | head -1 | '
            "          sed 's|/workspace/||;s|/|.|g;s|\\.py$||') && "
            '        if [ -n "$APP_MODULE" ]; then '
            '          START_CMD="uvicorn ${APP_MODULE}:app --host 0.0.0.0 --port 8000"; '
            "        else "
            '          START_CMD="uvicorn app:app --host 0.0.0.0 --port 8000"; '
            "        fi; "
            "      elif grep -q -i 'flask' /workspace/requirements.txt 2>/dev/null; then "
            '        START_CMD="flask run --host 0.0.0.0 --port 8000"; '
            "      elif grep -q -i 'django' /workspace/requirements.txt 2>/dev/null; then "
            '        START_CMD="python manage.py runserver 0.0.0.0:8000"; '
            "      fi; "
            # Node.js detection (use sh-compatible parsing with sed)
            "    elif [ -f /workspace/package.json ]; then "
            "      START_CMD=$(sed -n 's/.*\"start\" *: *\"\\(.*\\)\".*/\\1/p' /workspace/package.json | head -1) && "
            '      if [ -z "$START_CMD" ]; then '
            "        if [ -f /workspace/index.js ]; then "
            '          START_CMD="node index.js"; '
            "        elif [ -f /workspace/server.js ]; then "
            '          START_CMD="node server.js"; '
            "        elif [ -f /workspace/app.js ]; then "
            '          START_CMD="node app.js"; '
            "        fi; "
            "      fi; "
            # Go detection
            "    elif [ -f /workspace/go.mod ]; then "
            "      if [ -f /workspace/main.go ]; then "
            '        START_CMD="go run main.go"; '
            "      elif [ -d /workspace/cmd ]; then "
            '        FIRST_CMD=$(ls /workspace/cmd/ 2>/dev/null | head -1) && '
            '        if [ -n "$FIRST_CMD" ]; then '
            '          START_CMD="go run ./cmd/${FIRST_CMD}"; '
            "        fi; "
            "      fi; "
            # Ruby detection
            "    elif [ -f /workspace/Gemfile ]; then "
            "      if [ -f /workspace/config.ru ]; then "
            '        START_CMD="bundle exec rackup config.ru -p 8000 -o 0.0.0.0"; '
            "      fi; "
            # Rust detection
            "    elif [ -f /workspace/Cargo.toml ]; then "
            '      START_CMD="cargo run --release"; '
            "    fi && "
            # --- Retry nixpacks with detected start command ---
            '    if [ -n "$START_CMD" ]; then '
            '      echo "Detected start command: $START_CMD" && '
            '      if /tmp/nixpacks build /workspace --out /workspace --start-cmd "$START_CMD"; then '
            "        cp /workspace/.nixpacks/Dockerfile /workspace/Dockerfile && "
            "        sed -i 's/uv==$NIXPACKS_UV_VERSION/uv/g' /workspace/Dockerfile; "
            "      else "
            # --- Fallback: generate a simple Dockerfile ---
            '        echo "nixpacks retry failed, generating fallback Dockerfile..." && '
            "        FALLBACK_DOCKERFILE=/workspace/Dockerfile && "
            "        if [ -f /workspace/requirements.txt ] || [ -f /workspace/pyproject.toml ]; then "
            '          printf "FROM python:3.12-slim\\nWORKDIR /app\\nCOPY . .\\n" > $FALLBACK_DOCKERFILE && '
            "          if [ -f /workspace/requirements.txt ]; then "
            '            printf "RUN pip install --no-cache-dir -r requirements.txt\\n" >> $FALLBACK_DOCKERFILE; '
            "          elif [ -f /workspace/pyproject.toml ]; then "
            '            printf "RUN pip install --no-cache-dir .\\n" >> $FALLBACK_DOCKERFILE; '
            "          fi && "
            '          printf "EXPOSE 8000\\nCMD %s\\n" "$START_CMD" >> $FALLBACK_DOCKERFILE; '
            "        elif [ -f /workspace/package.json ]; then "
            '          printf "FROM node:20-slim\\nWORKDIR /app\\nCOPY package*.json ./\\nRUN npm ci --production\\nCOPY . .\\nEXPOSE 8000\\nCMD %s\\n" "$START_CMD" > $FALLBACK_DOCKERFILE; '  # noqa: E501
            "        elif [ -f /workspace/go.mod ]; then "
            '          printf "FROM golang:1.22-alpine\\nWORKDIR /app\\nCOPY go.* ./\\nRUN go mod download\\nCOPY . .\\nRUN go build -o /app/server .\\nEXPOSE 8000\\nCMD [\\\"/app/server\\\"]\\n" > $FALLBACK_DOCKERFILE; '  # noqa: E501
            "        fi; "
            "      fi; "
            "    else "
            # No start command detected — generate minimal fallback Dockerfile
            '      echo "No start command detected, generating fallback Dockerfile..." && '
            "      FALLBACK_DOCKERFILE=/workspace/Dockerfile && "
            "      if [ -f /workspace/requirements.txt ] || [ -f /workspace/pyproject.toml ]; then "
            '        printf "FROM python:3.12-slim\\nWORKDIR /app\\nCOPY . .\\n" > $FALLBACK_DOCKERFILE && '
            "        if [ -f /workspace/requirements.txt ]; then "
            '          printf "RUN pip install --no-cache-dir -r requirements.txt\\n" >> $FALLBACK_DOCKERFILE; '
            "        elif [ -f /workspace/pyproject.toml ]; then "
            '          printf "RUN pip install --no-cache-dir .\\n" >> $FALLBACK_DOCKERFILE; '
            "        fi && "
            '        printf "EXPOSE 8000\\nCMD [\\"python\\", \\"-c\\", \\"print(\'app running\')\\"]\\n" >> $FALLBACK_DOCKERFILE; '  # noqa: E501
            "      elif [ -f /workspace/package.json ]; then "
            '        printf "FROM node:20-slim\\nWORKDIR /app\\nCOPY package*.json ./\\nRUN npm ci --production\\nCOPY . .\\nEXPOSE 8000\\nCMD [\\"node\\", \\"index.js\\"]\\n" > $FALLBACK_DOCKERFILE; '  # noqa: E501
            "      elif [ -f /workspace/go.mod ]; then "
            '        printf "FROM golang:1.22-alpine\\nWORKDIR /app\\nCOPY go.* ./\\nRUN go mod download\\nCOPY . .\\nRUN go build -o /app/server .\\nEXPOSE 8000\\nCMD [\\\"/app/server\\\"]\\n" > $FALLBACK_DOCKERFILE; '  # noqa: E501
            "      else "
            '        echo "ERROR: Unable to detect language or start command" && exit 1; '
            "      fi; "
            "    fi; "
            "  fi; "
            "fi"
        )

        init_containers = [
            k8s_client_lib.V1Container(
                name="git-clone",
                image="alpine:3.20",
                command=["sh", "-c"],
                args=[f"apk add --no-cache git && {git_clone_cmd}"],
                env=[
                    k8s_client_lib.V1EnvVar(name="GIT_TERMINAL_PROMPT", value="0"),
                    k8s_client_lib.V1EnvVar(name="GIT_CONFIG_NOSYSTEM", value="1"),
                    k8s_client_lib.V1EnvVar(name="HOME", value="/tmp"),
                ],
                volume_mounts=[
                    k8s_client_lib.V1VolumeMount(name="workspace", mount_path="/workspace")
                ],
            ),
            k8s_client_lib.V1Container(
                name="nixpacks",
                image="alpine:3.20",
                command=["/bin/sh", "-c"],
                args=[nixpacks_cmd],
                volume_mounts=[
                    k8s_client_lib.V1VolumeMount(name="workspace", mount_path="/workspace")
                ],
            ),
        ]

        buildctl_container = k8s_client_lib.V1Container(
            name="buildctl",
            image="moby/buildkit:latest",
            command=["buildctl"],
            args=[
                "--addr", "tcp://buildkitd.haven-builds.svc.cluster.local:1234",
                "build",
                "--frontend", "dockerfile.v0",
                "--local", "context=/workspace",
                "--local", "dockerfile=/workspace",
                "--output", f"type=image,name={image_name},push=true,registry.insecure=true",
            ],
            volume_mounts=[
                k8s_client_lib.V1VolumeMount(name="workspace", mount_path="/workspace"),
                k8s_client_lib.V1VolumeMount(
                    name="docker-config", mount_path="/root/.docker", read_only=True
                ),
            ],
        )

        volumes = [
            k8s_client_lib.V1Volume(
                name="workspace", empty_dir=k8s_client_lib.V1EmptyDirVolumeSource()
            ),
            k8s_client_lib.V1Volume(
                name="docker-config",
                secret=k8s_client_lib.V1SecretVolumeSource(
                    secret_name="harbor-registry-secret",
                    items=[k8s_client_lib.V1KeyToPath(key=".dockerconfigjson", path="config.json")],
                ),
            ),
        ]

        pod_spec = k8s_client_lib.V1PodSpec(
            restart_policy="Never",
            init_containers=init_containers,
            containers=[buildctl_container],
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
