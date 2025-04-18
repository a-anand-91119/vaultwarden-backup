import os
import sys
import logging
import shutil
from datetime import datetime
import time
import schedule

# Use relative imports for components within the package
from .config_loader import ConfigLoader, ConfigError
from .docker_controller import DockerController
from .archiver import Archiver
from .store import BackupStore, TIMESTAMP_FORMAT

logger = logging.getLogger(__name__)

class VaultwardenBackupManager:
    """Orchestrates backup, restore, and scheduling."""

    def __init__(self, config_path):
        # No try/except here, let exceptions bubble up to main
        self.config_loader = ConfigLoader(config_path)
        self.config = self.config_loader.get_config()
        self.docker_controller = DockerController(self.config['vaultwarden']['container_name'])
        self.archiver = Archiver(self.config)
        self.store = BackupStore(self.config)

    def _set_permissions(self, target_path, uid, gid):
        """Sets ownership and permissions on the target path (recursive)."""
        abs_target_path = os.path.abspath(target_path)
        logger.info(f"Setting ownership of {abs_target_path} to {uid}:{gid}")
        try:
             # Need to walk the directory tree
             for root, dirs, files in os.walk(abs_target_path):
                 for d in dirs:
                     os.chown(os.path.join(root, d), uid, gid)
                 for f in files:
                     os.chown(os.path.join(root, f), uid, gid)
             # Set top-level directory ownership too
             os.chown(abs_target_path, uid, gid)

             # Set permissions (example: 700 for dir, 600 for files)
             logger.info(f"Setting permissions within {abs_target_path}...")
             os.chmod(abs_target_path, 0o700)
             for root, dirs, files in os.walk(abs_target_path):
                 for d in dirs:
                     os.chmod(os.path.join(root, d), 0o700)
                 for f in files:
                     try:
                        os.chmod(os.path.join(root, f), 0o600)
                     except OSError as pe:
                         logger.warning(f"Could not set permissions on file {os.path.join(root, f)}: {pe}")

             logger.info("Ownership and permissions set successfully.")
             return True
        except Exception as e:
             logger.error(f"Failed to set ownership/permissions on {abs_target_path}: {e}")
             logger.error("This likely requires running the script with sudo/root.")
             return False # Indicate failure, but allow restore to continue with warning

    def backup(self):
        """Performs a single backup run."""
        try:
            logger.info("--- Starting Vaultwarden Backup --- ")
            start_time = datetime.now()

            if not self.docker_controller.stop():
                logger.error("Skipping backup run because container stop failed.")
                self.docker_controller.start() # Attempt to restart
                return

            timestamp_str = start_time.strftime(TIMESTAMP_FORMAT)
            source_data_dir = self.config['vaultwarden']['data_dir']
            # Use store's dest_path directly
            dest_path_base = os.path.join(self.store.dest_path, f"vaultwarden-data-{timestamp_str}")
            final_backup_path = None

            try:
                final_backup_path = self.archiver.create(source_data_dir, dest_path_base)
                logger.info(f"Successfully created backup: {final_backup_path}")
            except Exception as e:
                logger.critical(f"Backup archive creation failed: {e}. Aborting backup run.")
                # Must ensure container is restarted
            finally:
                # Ensure container is started even if archive/retention fails
                if not self.docker_controller.start():
                     logger.error("Failed to restart Vaultwarden container after backup attempt!")

            # Apply retention policy only if backup succeeded
            if final_backup_path:
                self.store.apply_retention()
            else:
                 return # Explicitly return if backup creation failed

            end_time = datetime.now()
            logger.info(f"--- Vaultwarden Backup Finished --- Duration: {end_time - start_time}")

        except Exception as e:
            # Catch unexpected errors during the backup process
            logger.exception(f"An unexpected error occurred during the backup run: {e}")
            # Try to ensure container is started
            try:
                 self.docker_controller.start()
            except Exception as restart_e:
                 logger.error(f"Failed attempt to restart Vaultwarden after backup error: {restart_e}")

    def restore(self, backup_id, target_data_dir_override, force_yes):
        """Performs the restore process."""
        logger.warning("--- Starting Vaultwarden Restore --- THIS IS A DESTRUCTIVE OPERATION !!!")
        start_time = datetime.now()
        restore_temp_dir = self.config['backup']['restore']['temp_dir']
        target_data_dir = target_data_dir_override if target_data_dir_override else self.config['vaultwarden']['data_dir']
        restore_uid = self.config['backup']['restore'].get('owner_uid')
        restore_gid = self.config['backup']['restore'].get('owner_gid')
        cleanup_temp = True # Flag to control temp dir cleanup

        try:
            # --- Preparation ---
            logger.info(f"Target data directory for restore: {target_data_dir}")
            target_parent_dir = os.path.dirname(target_data_dir)
            if not os.path.isdir(target_parent_dir):
                raise FileNotFoundError(f"Parent directory of target does not exist: {target_parent_dir}")

            backup_file_to_restore = self.store.find_backup(backup_id)
            logger.info(f"Found backup to restore: {os.path.basename(backup_file_to_restore)}")

            # --- Temp Dir Handling ---
            if os.path.exists(restore_temp_dir):
                shutil.rmtree(restore_temp_dir)
            os.makedirs(restore_temp_dir, exist_ok=True)
            logger.info(f"Created temporary directory: {restore_temp_dir}")

            # --- Fetch and Decrypt ---
            local_archive_path_encrypted = os.path.join(restore_temp_dir, os.path.basename(backup_file_to_restore))
            # Use store method for fetching
            self.store.fetch_backup_local(backup_file_to_restore, local_archive_path_encrypted)

            local_archive_path_decrypted = local_archive_path_encrypted
            if local_archive_path_encrypted.endswith('.gpg'):
                local_archive_path_decrypted = local_archive_path_encrypted.replace('.gpg', '')
                self.archiver.decrypt(local_archive_path_encrypted, local_archive_path_decrypted)

            # --- Stop Container ---
            # Set internal mode hint (though stop doesn't use it currently)
            self.config['_internal_mode'] = 'restore'
            if not self.docker_controller.stop():
                 raise RuntimeError("Failed to stop Vaultwarden container. Restore cannot proceed safely.")
            self.config.pop('_internal_mode', None)

            # --- Confirmation ---
            if not force_yes and os.path.exists(target_data_dir):
                confirm = input(f"WARNING: Target data directory '{target_data_dir}' exists.\n"
                                f"This operation will DELETE IT and replace it with the contents of the backup.\n"
                                f"Proceed? (y/N): ")
                if confirm.lower() != 'y':
                    logger.warning("Restore aborted by user.")
                    self.docker_controller.start() # Try restart
                    return # Abort restore
                logger.info("User confirmed deletion of existing data.")
            elif os.path.exists(target_data_dir):
                logger.warning(f"Target data directory '{target_data_dir}' exists. Deleting due to --yes flag.")

            # --- Replace Data ---
            if os.path.exists(target_data_dir):
                logger.info(f"Deleting existing directory: {target_data_dir}")
                shutil.rmtree(target_data_dir)
            # Use archiver method for extraction
            self.archiver.extract(local_archive_path_decrypted, target_parent_dir)
            if not os.path.isdir(target_data_dir):
                raise RuntimeError(f"Extraction did not create the expected directory: {target_data_dir}")

            # --- Set Permissions ---
            permissions_ok = True
            if restore_uid is not None and restore_gid is not None:
                if not self._set_permissions(target_data_dir, restore_uid, restore_gid):
                     permissions_ok = False
                     logger.warning("Continuing restore, but Vaultwarden might fail to start if permissions are incorrect.")

            # --- Start Container ---
            if not self.docker_controller.start():
                 raise RuntimeError("Vaultwarden container failed to start after restore.")

            logger.info(f"--- Vaultwarden Restore Finished --- Duration: {datetime.now() - start_time}")
            logger.info("Please verify Vaultwarden functionality.")
            if not permissions_ok:
                 logger.warning("Permissions setting failed during restore. Manual check might be required.")

        except Exception as e:
            logger.critical(f"Restore failed: {e}", exc_info=True)
            logger.critical("The Vaultwarden data directory may be in an inconsistent state!")
            try: self.docker_controller.start() # Best effort restart
            except: pass
            cleanup_temp = False
            # Re-raise or exit? Let's re-raise for main to handle exit
            raise
        finally:
            if cleanup_temp and os.path.exists(restore_temp_dir):
                try:
                    logger.info(f"Cleaning up temporary directory: {restore_temp_dir}")
                    shutil.rmtree(restore_temp_dir)
                except OSError as e:
                    logger.warning(f"Could not clean up temporary directory {restore_temp_dir}: {e}")
            self.config.pop('_internal_mode', None)

    def run_scheduler(self):
        """Runs the backup function on a schedule."""
        interval = self.config['backup']['schedule']['interval_minutes']
        logger.info(f"Starting scheduler. Backup interval: {interval} minutes.")

        schedule.every(interval).minutes.do(self.backup)

        logger.info("Running initial backup job at startup...")
        self.backup()

        logger.info("Scheduler started. Waiting for next scheduled run...")
        while True:
            schedule.run_pending()
            time.sleep(60) 