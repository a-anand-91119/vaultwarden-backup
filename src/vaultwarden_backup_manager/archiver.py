import os
import shutil
import logging
from .utils import run_command # Use relative import

logger = logging.getLogger(__name__)

class Archiver:
    """Handles creation and encryption/decryption of archives."""

    def __init__(self, config):
        self.config = config
        # Safely get nested config values
        self.encrypt = config.get('backup', {}).get('encryption', {}).get('enabled', False)
        self.gpg_key_id = config.get('backup', {}).get('encryption', {}).get('gpg_key_id', '')

    def create(self, source_dir, dest_archive_path_no_ext):
        """Creates a tar.gz archive, optionally encrypts it."""
        archive_filename = f"{dest_archive_path_no_ext}.tar.gz"
        logger.info(f"Creating backup archive for {source_dir}...")
        if not os.path.isdir(source_dir):
            logger.error(f"Source data directory does not exist or is not a directory: {source_dir}")
            raise FileNotFoundError(f"Source data directory not found: {source_dir}")

        try:
            os.makedirs(os.path.dirname(dest_archive_path_no_ext), exist_ok=True)
            shutil.make_archive(dest_archive_path_no_ext, 'gztar', root_dir=os.path.dirname(source_dir), base_dir=os.path.basename(source_dir))
            logger.info(f"Archive created: {archive_filename}")

            if self.encrypt:
                encrypted_filename = f"{archive_filename}.gpg"
                logger.info(f"Encrypting archive to {encrypted_filename} using key {self.gpg_key_id}...")
                if not self.gpg_key_id:
                    raise ValueError("GPG Key ID is required for encryption but is missing.")
                gpg_command = [
                    'gpg', '--encrypt', '--recipient', self.gpg_key_id,
                    '--output', encrypted_filename, archive_filename
                ]
                run_command(gpg_command)
                logger.info("Encryption complete.")
                os.remove(archive_filename)
                logger.info(f"Removed unencrypted archive: {archive_filename}")
                return encrypted_filename
            else:
                return archive_filename

        except Exception as e:
            logger.error(f"Failed to create backup archive: {e}")
            # Cleanup potentially incomplete files
            if os.path.exists(archive_filename):
                logger.debug(f"Cleaning up potentially incomplete file: {archive_filename}")
                os.remove(archive_filename)
            # Only check for encrypted file if encryption was enabled
            if self.encrypt:
                encrypted_filename = f"{archive_filename}.gpg"
                if os.path.exists(encrypted_filename):
                    logger.debug(f"Cleaning up potentially incomplete encrypted file: {encrypted_filename}")
                    os.remove(encrypted_filename)
            raise

    def decrypt(self, source_archive_path, dest_decrypted_path):
         """Decrypts a GPG encrypted archive."""
         if not source_archive_path.endswith('.gpg'):
              logger.warning(f"Source file {source_archive_path} does not end with .gpg, assuming not encrypted.")
              return False # Indicate no decryption happened

         logger.info(f"Decrypting {os.path.basename(source_archive_path)}...")
         try:
            gpg_command = [
                'gpg', '--decrypt', '--output', dest_decrypted_path,
                source_archive_path
            ]
            run_command(gpg_command)
            logger.info(f"Decryption complete: {os.path.basename(dest_decrypted_path)}")
            return True # Indicate decryption happened
         except Exception as e:
             logger.error(f"Decryption failed: {e}")
             raise

    def extract(self, source_archive_path, dest_dir):
        """Extracts a tar.gz archive."""
        logger.info(f"Extracting '{os.path.basename(source_archive_path)}' to {dest_dir}...")
        try:
            shutil.unpack_archive(source_archive_path, dest_dir)
            logger.info("Extraction complete.")
        except Exception as e:
            logger.error(f"Extraction failed: {e}")
            raise 