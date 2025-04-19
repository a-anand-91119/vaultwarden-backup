import pytest
import subprocess
from unittest.mock import patch, MagicMock

# Adjust import based on project structure
from vaultwarden_backup_manager.utils import run_command


# --- Test run_command ---

def test_run_command_success():
    """Tests successful command execution."""
    cmd = ["echo", "hello"]
    mock_result = MagicMock()
    mock_result.stdout = "hello\n"
    mock_result.stderr = ""
    mock_result.returncode = 0

    with patch("subprocess.run", return_value=mock_result) as mock_subprocess_run:
        result = run_command(cmd, capture_output=True)

        mock_subprocess_run.assert_called_once_with(
            cmd, cwd=None, check=True, capture_output=True, text=True, shell=False
        )
        assert result == mock_result


def test_run_command_success_no_capture():
    """Tests successful command execution without capturing output."""
    cmd = ["touch", "a_file"]
    mock_result = MagicMock()
    mock_result.returncode = 0

    with patch("subprocess.run", return_value=mock_result) as mock_subprocess_run:
        result = run_command(cmd, capture_output=False)  # Default

        mock_subprocess_run.assert_called_once_with(
            cmd, cwd=None, check=True, capture_output=False, text=True, shell=False
        )
        assert result == mock_result


def test_run_command_called_process_error():
    """Tests handling of CalledProcessError."""
    cmd = ["false"]  # Command that typically exits with non-zero code
    error = subprocess.CalledProcessError(1, cmd, output="error output", stderr="error stderr")

    with patch("subprocess.run", side_effect=error) as mock_subprocess_run:
        with pytest.raises(subprocess.CalledProcessError):
            run_command(cmd, capture_output=True)

        mock_subprocess_run.assert_called_once_with(
            cmd, cwd=None, check=True, capture_output=True, text=True, shell=False
        )


def test_run_command_called_process_error_no_check():
    """Tests that CalledProcessError is NOT raised if check=False."""
    cmd = ["false"]
    mock_result = MagicMock()
    mock_result.returncode = 1  # Simulate failure
    mock_result.stdout = ""
    mock_result.stderr = "Something went wrong"

    # Simulate the error *not* being raised by subprocess.run itself when check=False
    with patch("subprocess.run", return_value=mock_result) as mock_subprocess_run:
        result = run_command(cmd, check=False, capture_output=True)

        mock_subprocess_run.assert_called_once_with(
            cmd, cwd=None, check=False, capture_output=True, text=True, shell=False
        )
        assert result.returncode == 1  # Check the returned result directly


def test_run_command_file_not_found_error():
    """Tests handling of FileNotFoundError."""
    cmd = ["non_existent_command"]
    error = FileNotFoundError(f"[Errno 2] No such file or directory: '{cmd[0]}'")

    with patch("subprocess.run", side_effect=error) as mock_subprocess_run:
        with pytest.raises(FileNotFoundError):
            run_command(cmd)

        mock_subprocess_run.assert_called_once_with(
            cmd, cwd=None, check=True, capture_output=False, text=True, shell=False
        )


def test_run_command_with_cwd():
    """Tests running command with a specific current working directory."""
    cmd = ["ls"]
    cwd = "/tmp"
    mock_result = MagicMock()
    mock_result.returncode = 0

    with patch("subprocess.run", return_value=mock_result) as mock_subprocess_run:
        result = run_command(cmd, cwd=cwd)

        mock_subprocess_run.assert_called_once_with(
            cmd, cwd=cwd, check=True, capture_output=False, text=True, shell=False
        )
        assert result == mock_result
