import subprocess
import logging

logger = logging.getLogger(__name__)

def run_command(cmd_list, cwd=None, check=True, capture_output=False):
    """Runs an external command."""
    logger.debug(f"Running command: {' '.join(cmd_list)}")
    try:
        result = subprocess.run(
            cmd_list,
            cwd=cwd,
            check=check,
            capture_output=capture_output,
            text=True,
            shell=False
        )
        if capture_output:
            logger.debug(f"Command stdout: {result.stdout}")
            logger.debug(f"Command stderr: {result.stderr}")
        return result
    except subprocess.CalledProcessError as e:
        cmd_str = ' '.join(cmd_list)
        logger.error(f"Command failed: {cmd_str}")
        logger.error(f"Return code: {e.returncode}")
        if e.output:
             logger.error(f"Output: {e.output}")
        if e.stderr:
             logger.error(f"Stderr: {e.stderr}")
        raise
    except FileNotFoundError:
        logger.error(f"Command not found: {cmd_list[0]}. Is it installed and in PATH?")
        raise 