"""Tests for build-only pipeline mode (deploy=False → BUILT status)."""


from app.models.deployment import DeploymentStatus


class TestBuildOnlyMode:
    """Test that BUILT status exists and pipeline supports deploy parameter."""

    def test_built_status_enum_exists(self):
        assert hasattr(DeploymentStatus, "BUILT")
        assert DeploymentStatus.BUILT.value == "built"

    def test_all_deployment_statuses(self):
        expected = {"pending", "building", "built", "deploying", "running", "failed"}
        actual = {s.value for s in DeploymentStatus}
        assert expected == actual

    def test_deployment_status_ordering(self):
        """Status values should cover full lifecycle."""
        statuses = [s.value for s in DeploymentStatus]
        # BUILT should be between BUILDING and DEPLOYING
        building_idx = statuses.index("building")
        built_idx = statuses.index("built")
        deploying_idx = statuses.index("deploying")
        assert building_idx < built_idx < deploying_idx

    def test_pipeline_accepts_deploy_param(self):
        """run_pipeline function should accept deploy parameter."""
        import inspect

        from app.services.pipeline import run_pipeline

        sig = inspect.signature(run_pipeline)
        assert "deploy" in sig.parameters
        deploy_param = sig.parameters["deploy"]
        assert deploy_param.default is True

    def test_pipeline_deploy_false_path_exists(self):
        """Pipeline code should handle deploy=False case."""
        import ast
        from pathlib import Path

        pipeline_file = Path(__file__).parent.parent / "app" / "services" / "pipeline.py"
        source = pipeline_file.read_text()
        tree = ast.parse(source)

        # Check that 'if not deploy' appears in the function
        found_deploy_check = False
        for node in ast.walk(tree):
            if (  # noqa: SIM102
                isinstance(node, ast.If)
                and isinstance(node.test, ast.UnaryOp)
                and isinstance(node.test.op, ast.Not)
                and isinstance(node.test.operand, ast.Name)
                and node.test.operand.id == "deploy"
            ):
                found_deploy_check = True
                break
        assert found_deploy_check, "Pipeline should have 'if not deploy:' branch for build-only mode"


class TestDeployImageEndpoint:
    """Test the deploy-image endpoint exists and has correct parameters."""

    def test_deploy_image_endpoint_registered(self):
        """deploy-image endpoint should be registered on the deployments router."""
        from app.routers.deployments import router

        paths = [route.path for route in router.routes]
        # The path will be relative to the router prefix
        assert any("deploy-image" in p for p in paths), f"deploy-image not found in routes: {paths}"

    def test_build_trigger_has_deploy_param(self):
        """Build trigger endpoint should accept deploy query parameter."""
        import inspect

        from app.routers.deployments import trigger_build

        sig = inspect.signature(trigger_build)
        assert "deploy" in sig.parameters

    def test_deploy_param_exists(self):
        """Build trigger should have deploy parameter."""
        import inspect

        from app.routers.deployments import trigger_build

        sig = inspect.signature(trigger_build)
        assert "deploy" in sig.parameters


class TestSSEHeartbeatFormat:
    """Test that SSE heartbeat uses data: format."""

    def test_heartbeat_uses_data_prefix(self):
        """SSE heartbeat should use 'data: [heartbeat]' format for UI parser compatibility."""
        from pathlib import Path

        deployments_file = Path(__file__).parent.parent / "app" / "routers" / "deployments.py"
        source = deployments_file.read_text()

        # Should NOT have ': heartbeat' (old format)
        assert ': heartbeat\\n\\n"' not in source, "Old heartbeat format still present"

        # Should have 'data: [heartbeat]' (new format)
        assert 'data: [heartbeat]\\n\\n"' in source, "New heartbeat format not found"
