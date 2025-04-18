import pytest
from unittest.mock import patch, MagicMock
import logging
import subprocess # Needed for CalledProcessError

# Adjust the import path based on the project structure
from vaultwarden_backup_manager.docker_controller import DockerController

# Disable logging for tests unless specifically needed
logging.disable(logging.CRITICAL)

# Constants for tests
CONTAINER_NAME = "test_vaultwarden_container"

# Can still use fixtures if desired, or setup methods within the class
@pytest.fixture
def controller_instance():
    """Pytest fixture to create a DockerController instance."""
    return DockerController(CONTAINER_NAME)

class TestDockerController:

    # You could use setup_method/teardown_method here instead of a fixture
    # def setup_method(self, method):
    #    self.controller = DockerController(CONTAINER_NAME)

    @patch('vaultwarden_backup_manager.docker_controller.run_command')
    def test_stop_success(self, mock_run_command, controller_instance):
        """Test successful container stop."""
        mock_run_command.return_value = MagicMock() # Simulate successful run
        result = controller_instance.stop()
        mock_run_command.assert_called_once_with(['docker', 'stop', CONTAINER_NAME])
        assert result is True

    @patch('vaultwarden_backup_manager.docker_controller.run_command')
    def test_start_success(self, mock_run_command, controller_instance):
        """Test successful container start."""
        mock_run_command.return_value = MagicMock() # Simulate successful run
        result = controller_instance.start()
        mock_run_command.assert_called_once_with(['docker', 'start', CONTAINER_NAME])
        assert result is True

    @patch('vaultwarden_backup_manager.docker_controller.run_command')
    def test_stop_failure(self, mock_run_command, controller_instance):
        """Test container stop failure when run_command raises an exception."""
        mock_run_command.side_effect = subprocess.CalledProcessError(
            returncode=1, cmd=['docker', 'stop', CONTAINER_NAME]
        )
        result = controller_instance.stop()
        mock_run_command.assert_called_once_with(['docker', 'stop', CONTAINER_NAME])
        assert result is False

    @patch('vaultwarden_backup_manager.docker_controller.run_command')
    def test_start_failure(self, mock_run_command, controller_instance):
        """Test container start failure when run_command raises an exception."""
        mock_run_command.side_effect = Exception("Docker daemon not running")
        result = controller_instance.start()
        mock_run_command.assert_called_once_with(['docker', 'start', CONTAINER_NAME])
        assert result is False

    # No patch needed for this test as it doesn't call run_command
    def test_init_stores_container_name(self, controller_instance):
        """Test if the container name is stored correctly during initialization."""
        assert controller_instance.container_name == CONTAINER_NAME
