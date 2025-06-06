import logging
from .utils import run_command

logger = logging.getLogger(__name__)


class DockerController:
    """Controls the Vaultwarden Docker container."""

    def __init__(self, skip_ops, container_name):
        self.container_name = container_name
        self.skip_start_stop = bool(skip_ops)

    def _run_docker_command(self, action):
        if self.skip_start_stop:
            logger.info(f"Docker start/stop disabled. Skipping docker command: {action}")
            return True

        command = ['docker', action, self.container_name]
        logger.info(f"{action.capitalize()}ing Vaultwarden container '{self.container_name}'...")
        try:
            run_command(command)
            logger.info(f"Vaultwarden container '{self.container_name}' {action} completed.")
            return True
        except Exception as e:
            logger.error(f"Failed to {action} Vaultwarden container '{self.container_name}': {e}")
            return False

    def stop(self):
        return self._run_docker_command("stop")

    def start(self):
        return self._run_docker_command("start")
