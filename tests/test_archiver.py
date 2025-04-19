import pytest
import os
import shutil
from unittest.mock import patch, MagicMock, call
import subprocess

from vaultwarden_backup_manager.archiver import Archiver


# --- Fixtures ---

@pytest.fixture
def config_no_encrypt():
    """Config with encryption disabled."""
    return {'backup': {'encryption': {'enabled': False}}}


@pytest.fixture
def config_encrypt_with_key():
    """Config with encryption enabled and a GPG key ID."""
    return {
        'backup': {
            'encryption': {
                'enabled': True,
                'gpg_key_id': 'test_key_id'
            }
        }
    }


@pytest.fixture
def config_encrypt_no_key():
    """Config with encryption enabled but no GPG key ID."""
    return {
        'backup': {
            'encryption': {
                'enabled': True,
                'gpg_key_id': ''  # Missing key
            }
        }
    }


@pytest.fixture
def mock_run_command():
    with patch('vaultwarden_backup_manager.archiver.run_command') as mock_cmd:
        yield mock_cmd


@pytest.fixture
def mock_shutil():
    with patch('vaultwarden_backup_manager.archiver.shutil') as mock_sh:
        yield mock_sh


@pytest.fixture
def mock_os():
    # Mock os functions used by the archiver
    with patch('vaultwarden_backup_manager.archiver.os.path.isdir') as mock_isdir, \
            patch('vaultwarden_backup_manager.archiver.os.path.exists') as mock_exists, \
            patch('vaultwarden_backup_manager.archiver.os.makedirs') as mock_makedirs, \
            patch('vaultwarden_backup_manager.archiver.os.remove') as mock_remove:
        # Configure mocks
        # mock_dirname.side_effect = os.path.dirname # Remove unnecessary mock
        # mock_basename.side_effect = os.path.basename # Remove unnecessary mock
        yield {
            'isdir': mock_isdir,
            'exists': mock_exists,
            'makedirs': mock_makedirs,
            'remove': mock_remove,
            # 'dirname': mock_dirname, # Remove from yielded dict
            # 'basename': mock_basename # Remove from yielded dict
        }


# --- Test Archiver.create ---
class TestArchiver:

    def test_create_success_no_encrypt(self, config_no_encrypt, mock_shutil, mock_os, tmp_path):
        """Test successful archive creation without encryption."""
        archiver = Archiver(config_no_encrypt)
        source_dir = tmp_path / "source_data"
        source_dir.mkdir()
        dest_base = tmp_path / "backups" / "backup-20230101T120000"
        expected_archive = f"{dest_base}.tar.gz"

        mock_os['isdir'].return_value = True

        result = archiver.create(str(source_dir), str(dest_base))

        mock_os['isdir'].assert_called_once_with(str(source_dir))
        mock_os['makedirs'].assert_called_once_with(str(tmp_path / "backups"), exist_ok=True)
        mock_shutil.make_archive.assert_called_once_with(
            str(dest_base), 'gztar', root_dir=str(tmp_path), base_dir="source_data"
        )
        assert result == expected_archive
        mock_os['remove'].assert_not_called()

    def test_create_success_with_encrypt(self, config_encrypt_with_key, mock_run_command, mock_shutil, mock_os,
                                         tmp_path):
        """Test successful archive creation with encryption."""
        archiver = Archiver(config_encrypt_with_key)
        source_dir = tmp_path / "source_data"
        source_dir.mkdir()
        dest_base = tmp_path / "backups" / "backup-20230101T120000"
        unencrypted_archive = f"{dest_base}.tar.gz"
        encrypted_archive = f"{unencrypted_archive}.gpg"

        mock_os['isdir'].return_value = True

        result = archiver.create(str(source_dir), str(dest_base))

        mock_os['isdir'].assert_called_once_with(str(source_dir))
        mock_os['makedirs'].assert_called_once()  # Called in the no_encrypt path too
        mock_shutil.make_archive.assert_called_once()  # Called in the no_encrypt path

        expected_gpg_cmd = [
            'gpg', '--encrypt', '--recipient', 'test_key_id',
            '--output', encrypted_archive, unencrypted_archive
        ]
        mock_run_command.assert_called_once_with(expected_gpg_cmd)
        mock_os['remove'].assert_called_once_with(unencrypted_archive)
        assert result == encrypted_archive

    def test_create_fail_source_not_dir(self, config_no_encrypt, mock_os, tmp_path):
        """Test create failure if source directory doesn't exist or isn't a directory."""
        archiver = Archiver(config_no_encrypt)
        source_dir = tmp_path / "non_existent"
        dest_base = tmp_path / "backup"

        mock_os['isdir'].return_value = False

        with pytest.raises(FileNotFoundError, match=f"Source data directory not found: {source_dir}"):
            archiver.create(str(source_dir), str(dest_base))
        mock_os['isdir'].assert_called_once_with(str(source_dir))

    def test_create_fail_encrypt_no_key(self, config_encrypt_no_key, mock_shutil, mock_os, tmp_path):
        """Test create failure if encryption is enabled but GPG key ID is missing."""
        archiver = Archiver(config_encrypt_no_key)
        source_dir = tmp_path / "source_data"
        source_dir.mkdir()
        dest_base = tmp_path / "backup"
        unencrypted_archive = f"{dest_base}.tar.gz"

        mock_os['isdir'].return_value = True
        mock_os['exists'].return_value = True  # Simulate archive created before fail

        with pytest.raises(ValueError, match="GPG Key ID is required for encryption but is missing."):
            archiver.create(str(source_dir), str(dest_base))

        mock_shutil.make_archive.assert_called_once()
        # Check cleanup - Since encryption was enabled, it should try to remove both
        # Assuming mock_os['exists'] makes both checks return True
        assert mock_os['remove'].call_count == 2
        encrypted_archive = f"{unencrypted_archive}.gpg"
        mock_os['remove'].assert_has_calls([
            call(unencrypted_archive),
            call(encrypted_archive)
        ], any_order=True)

    def test_create_fail_make_archive_exception(self, config_no_encrypt, mock_shutil, mock_os, tmp_path):
        """Test cleanup if shutil.make_archive raises an exception."""
        archiver = Archiver(config_no_encrypt)
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        dest_base = tmp_path / "backup"
        archive_path = f"{dest_base}.tar.gz"

        mock_os['isdir'].return_value = True
        mock_shutil.make_archive.side_effect = OSError("Disk full")
        mock_os['exists'].return_value = True  # Simulate file exists for cleanup

        with pytest.raises(OSError, match="Disk full"):
            archiver.create(str(source_dir), str(dest_base))

        mock_shutil.make_archive.assert_called_once()
        mock_os['remove'].assert_called_once_with(archive_path)

    def test_create_fail_gpg_exception(self, config_encrypt_with_key, mock_run_command, mock_shutil, mock_os, tmp_path):
        """Test cleanup if gpg command raises an exception."""
        archiver = Archiver(config_encrypt_with_key)
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        dest_base = tmp_path / "backup"
        archive_path = f"{dest_base}.tar.gz"
        encrypted_path = f"{archive_path}.gpg"

        mock_os['isdir'].return_value = True
        mock_run_command.side_effect = subprocess.CalledProcessError(1, "gpg failed")
        # Simulate both files potentially existing during cleanup check
        mock_os['exists'].side_effect = [True, True]

        with pytest.raises(subprocess.CalledProcessError, match="gpg failed"):
            archiver.create(str(source_dir), str(dest_base))

        mock_shutil.make_archive.assert_called_once()
        mock_run_command.assert_called_once()
        # Check cleanup calls
        assert mock_os['remove'].call_count == 2
        mock_os['remove'].assert_has_calls([call(archive_path), call(encrypted_path)], any_order=True)

    # --- Test Archiver.decrypt ---

    def test_decrypt_success(self, config_encrypt_with_key, mock_run_command, mock_os):
        """Test successful decryption."""
        archiver = Archiver(config_encrypt_with_key)  # Config doesn't matter for decrypt method itself
        source_gpg = "/path/to/archive.tar.gz.gpg"
        dest_decrypted = "/path/to/archive.tar.gz"

        # mock_os['basename'].side_effect = os.path.basename # Remove unnecessary mock setup

        result = archiver.decrypt(source_gpg, dest_decrypted)

        expected_gpg_cmd = ['gpg', '--decrypt', '--output', dest_decrypted, source_gpg]
        mock_run_command.assert_called_once_with(expected_gpg_cmd)
        assert result is True

    def test_decrypt_skip_not_gpg(self, config_encrypt_with_key, mock_run_command, mock_os):
        """Test that decryption is skipped if the file doesn't end with .gpg."""
        archiver = Archiver(config_encrypt_with_key)
        source_not_gpg = "/path/to/archive.tar.gz"
        dest_decrypted = "/path/to/decrypted_archive.tar.gz"

        result = archiver.decrypt(source_not_gpg, dest_decrypted)

        mock_run_command.assert_not_called()
        assert result is False

    def test_decrypt_fail_gpg_exception(self, config_encrypt_with_key, mock_run_command, mock_os):
        """Test decryption failure if gpg command raises an exception."""
        archiver = Archiver(config_encrypt_with_key)
        source_gpg = "/path/to/archive.tar.gz.gpg"
        dest_decrypted = "/path/to/archive.tar.gz"

        mock_run_command.side_effect = subprocess.CalledProcessError(1, "gpg decrypt failed")

        with pytest.raises(subprocess.CalledProcessError, match="gpg decrypt failed"):
            archiver.decrypt(source_gpg, dest_decrypted)

        mock_run_command.assert_called_once()

    # --- Test Archiver.extract ---

    def test_extract_success(self, config_no_encrypt, mock_shutil, mock_os):
        """Test successful extraction."""
        archiver = Archiver(config_no_encrypt)  # Config doesn't matter
        source_archive = "/path/to/archive.tar.gz"
        dest_dir = "/path/to/extract/here"

        # mock_os['basename'].side_effect = os.path.basename # Remove unnecessary mock setup

        archiver.extract(source_archive, dest_dir)

        mock_shutil.unpack_archive.assert_called_once_with(source_archive, dest_dir)

    def test_extract_fail_exception(self, config_no_encrypt, mock_shutil, mock_os):
        """Test extraction failure."""
        archiver = Archiver(config_no_encrypt)
        source_archive = "/path/to/archive.tar.gz"
        dest_dir = "/path/to/extract/here"

        mock_shutil.unpack_archive.side_effect = shutil.ReadError("Invalid archive")

        with pytest.raises(shutil.ReadError, match="Invalid archive"):
            archiver.extract(source_archive, dest_dir)

        mock_shutil.unpack_archive.assert_called_once_with(source_archive, dest_dir)
