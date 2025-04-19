import pytest
from unittest.mock import patch, MagicMock
import logging
import subprocess  # Needed for CalledProcessError

# Adjust the import path based on the project structure
from vaultwarden_backup_manager.docker_controller import DockerController

# Disable logging for tests unless specifically needed
logging.disable(logging.CRITICAL)

# Constants for tests
CONTAINER_NAME = "test_vaultwarden_container"


# Parameterize tests for skip_ops True/False
@pytest.fixture(params=[False, True], ids=["ops_enabled", "ops_disabled"])
def skip_start_stop_param(request):
    return request.param

@pytest.fixture
def controller_instance(skip_start_stop_param): # Use the renamed parameterized fixture
    """Pytest fixture to create a DockerController instance, parameterized for skip_ops."""
    return DockerController(skip_ops=skip_start_stop_param, container_name=CONTAINER_NAME)

class TestDockerController:

    # You could use setup_method/teardown_method here instead of a fixture
    # def setup_method(self, method):
    #    self.controller = DockerController(skip_ops=False, container_name=CONTAINER_NAME) # Example

    @patch('vaultwarden_backup_manager.docker_controller.run_command')
    def test_stop_success(self, mock_run_command, controller_instance, skip_start_stop_param):
        """Test successful container stop (or skip)."""
        mock_run_command.return_value = MagicMock()  # Simulate successful run
        result = controller_instance.stop()

        if skip_start_stop_param:
            mock_run_command.assert_not_called()
        else:
            mock_run_command.assert_called_once_with(['docker', 'stop', CONTAINER_NAME])
        assert result is True # Should always return True on success/skip

    @patch('vaultwarden_backup_manager.docker_controller.run_command')
    def test_start_success(self, mock_run_command, controller_instance, skip_start_stop_param):
        """Test successful container start (or skip)."""
        mock_run_command.return_value = MagicMock()  # Simulate successful run
        result = controller_instance.start()

        if skip_start_stop_param:
            mock_run_command.assert_not_called()
        else:
            mock_run_command.assert_called_once_with(['docker', 'start', CONTAINER_NAME])
        assert result is True # Should always return True on success/skip

    @patch('vaultwarden_backup_manager.docker_controller.run_command')
    def test_stop_failure(self, mock_run_command, controller_instance, skip_start_stop_param):
        """Test container stop failure when run_command raises an exception (if ops enabled)."""
        mock_run_command.side_effect = subprocess.CalledProcessError(
            returncode=1, cmd=['docker', 'stop', CONTAINER_NAME]
        )
        result = controller_instance.stop()

        if skip_start_stop_param:
            mock_run_command.assert_not_called()
            assert result is True # Skipping always returns True
        else:
            mock_run_command.assert_called_once_with(['docker', 'stop', CONTAINER_NAME])
            assert result is False

    @patch('vaultwarden_backup_manager.docker_controller.run_command')
    def test_start_failure(self, mock_run_command, controller_instance, skip_start_stop_param):
        """Test container start failure when run_command raises an exception (if ops enabled)."""
        mock_run_command.side_effect = Exception("Docker daemon not running")
        result = controller_instance.start()

        if skip_start_stop_param:
            mock_run_command.assert_not_called()
            assert result is True # Skipping always returns True
        else:
            mock_run_command.assert_called_once_with(['docker', 'start', CONTAINER_NAME])
            assert result is False

    # No patch needed for this test as it doesn't call run_command
    def test_init_stores_container_name_and_skip_ops(self, controller_instance, skip_start_stop_param):
        """Test if container name and skip_ops are stored correctly."""
        assert controller_instance.container_name == CONTAINER_NAME
        assert controller_instance.skip_start_stop == skip_start_stop_param
