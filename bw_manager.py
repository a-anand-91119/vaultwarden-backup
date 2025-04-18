#!/usr/bin/env python3

import argparse
import logging
import os
import subprocess
import sys
import shutil
from datetime import datetime, timedelta
import re
import glob
import yaml
import schedule
import time

# --- Constants ---
TIMESTAMP_FORMAT = "%Y%m%dT%H%M%S"
BACKUP_FILENAME_PATTERN = "vaultwarden-data-*.tar.gz*"
DEFAULT_LOG_FILE = "vaultwarden_manager.log"

# --- Logging Setup ---
log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Console Handler
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(log_formatter)
logger.addHandler(stream_handler)

# File Handler (will be added after config load)
file_handler = None

# --- Helper Functions ---

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
        logger.error(f"Command not found: {cmd_list[0]}. Is Docker installed and in PATH?")
        raise

def load_config(config_path):
    """Loads configuration from a YAML file."""
    if not os.path.exists(config_path):
        logger.error(f"Configuration file not found: {config_path}")
        sys.exit(1)
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)

        # --- Validation for Vaultwarden Structure ---
        if not isinstance(config, dict):
             raise ValueError("Config file is not a valid YAML dictionary.")

        # Check top-level keys
        if 'vaultwarden' not in config or not isinstance(config['vaultwarden'], dict):
            raise ValueError("Missing or invalid 'vaultwarden' section in config.")
        if 'backup' not in config or not isinstance(config['backup'], dict):
            raise ValueError("Missing or invalid 'backup' section in config.")

        # Check vaultwarden section
        vw_cfg = config['vaultwarden']
        if 'container_name' not in vw_cfg or not isinstance(vw_cfg['container_name'], str):
            raise ValueError("Missing or invalid 'container_name' (string) in 'vaultwarden' section.")
        if 'data_dir' not in vw_cfg or not isinstance(vw_cfg['data_dir'], str):
             raise ValueError("Missing or invalid 'data_dir' (string) in 'vaultwarden' section.")

        # Check backup section structure
        backup_cfg = config['backup']
        required_backup_keys = ['schedule', 'destination', 'retention', 'restore']
        for key in required_backup_keys:
            if key not in backup_cfg or not isinstance(backup_cfg[key], dict):
                 raise ValueError(f"Missing or invalid '{key}' subsection in 'backup' section.")

        # Check schedule sub-keys
        schedule_cfg = backup_cfg['schedule']
        if 'interval_minutes' not in schedule_cfg or not isinstance(schedule_cfg['interval_minutes'], int) or schedule_cfg['interval_minutes'] <= 0:
             raise ValueError("Missing or invalid 'interval_minutes' (positive integer) in 'backup.schedule' section.")

        # Check destination sub-keys
        dest_cfg = backup_cfg['destination']
        if 'type' not in dest_cfg or not isinstance(dest_cfg['type'], str):
            raise ValueError("Missing or invalid 'type' (string) in 'backup.destination' section.")
        if 'path' not in dest_cfg or not isinstance(dest_cfg['path'], str):
            raise ValueError("Missing or invalid 'path' (string) in 'backup.destination' section.")
        if dest_cfg['type'] != 'local':
             logger.warning(f"Destination type '{dest_cfg['type']}' is not yet fully supported.")

        # Check retention sub-keys
        ret_cfg = backup_cfg['retention']
        ret_keys = ['daily', 'weekly', 'monthly']
        for key in ret_keys:
            if key not in ret_cfg or not isinstance(ret_cfg[key], int) or ret_cfg[key] < 0:
                 raise ValueError(f"Invalid or missing '{key}' value in 'backup.retention'. Must be a non-negative integer.")

        # Check restore sub-keys
        restore_cfg = backup_cfg['restore']
        if 'temp_dir' not in restore_cfg or not isinstance(restore_cfg['temp_dir'], str):
            raise ValueError("Missing or invalid 'temp_dir' (string) in 'backup.restore' section.")

        # Check restore permissions (optional, but check type if present)
        uid = restore_cfg.get('owner_uid')
        gid = restore_cfg.get('owner_gid')
        if uid is not None and not isinstance(uid, int):
            raise ValueError("Invalid type for 'owner_uid' in 'backup.restore'. Expected an integer or null/omitted.")
        if gid is not None and not isinstance(gid, int):
             raise ValueError("Invalid type for 'owner_gid' in 'backup.restore'. Expected an integer or null/omitted.")

        # Check encryption settings (optional section)
        enc_cfg = backup_cfg.get('encryption', {})
        if enc_cfg.get('enabled', False):
            if not enc_cfg.get('gpg_key_id') or not isinstance(enc_cfg['gpg_key_id'], str):
                 raise ValueError("Missing or invalid 'gpg_key_id' (string) in 'backup.encryption' when 'enabled' is true.")

        # No defaults needed as keys are checked now
        return config
    except (yaml.YAMLError, ValueError, KeyError, TypeError) as e:
        logger.error(f"Error reading or validating configuration file '{config_path}': {e}")
        sys.exit(1)

def manage_vaultwarden_container(config, action):
    """Starts or stops the Vaultwarden Docker container."""
    container_name = config['vaultwarden']['container_name']
    command = ['docker', action, container_name]

    logger.info(f"{action.capitalize()}ing Vaultwarden container '{container_name}'...")
    try:
        run_command(command)
        logger.info(f"Vaultwarden container '{container_name}' {action} completed.")
        return True
    except Exception as e:
        logger.error(f"Failed to {action} Vaultwarden container '{container_name}': {e}")
        if action == "stop" and config.get('_internal_mode') == 'restore':
             sys.exit(1)
        return False

def create_backup_archive(config, timestamp_str):
    """Creates a compressed tar archive of the Vaultwarden data directory."""
    vw_cfg = config['vaultwarden']
    backup_cfg = config['backup']
    source_data_dir = vw_cfg['data_dir']
    dest_path = backup_cfg['destination']['path']
    encrypt = backup_cfg.get('encryption', {}).get('enabled', False)
    gpg_key_id = backup_cfg.get('encryption', {}).get('gpg_key_id', '')

    base_filename = f"vaultwarden-data-{timestamp_str}"
    archive_basename = os.path.join(dest_path, base_filename)
    archive_filename = f"{archive_basename}.tar.gz"

    logger.info(f"Creating backup archive for {source_data_dir}...")
    if not os.path.isdir(source_data_dir):
        logger.error(f"Source data directory does not exist or is not a directory: {source_data_dir}")
        raise FileNotFoundError(f"Source data directory not found: {source_data_dir}")

    try:
        os.makedirs(dest_path, exist_ok=True)
        shutil.make_archive(archive_basename, 'gztar', root_dir=os.path.dirname(source_data_dir), base_dir=os.path.basename(source_data_dir))
        logger.info(f"Archive created: {archive_filename}")

        if encrypt:
            if not gpg_key_id:
                 raise ValueError("GPG Key ID is required for encryption but not found.")
            encrypted_filename = f"{archive_filename}.gpg"
            logger.info(f"Encrypting archive to {encrypted_filename} using key {gpg_key_id}...")
            gpg_command = [
                'gpg', '--encrypt', '--recipient', gpg_key_id,
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
        if os.path.exists(archive_filename):
            os.remove(archive_filename)
        encrypted_filename = f"{archive_filename}.gpg"
        if os.path.exists(encrypted_filename):
             os.remove(encrypted_filename)
        raise

def apply_retention_policy(config):
    """Deletes old backups based on the retention policy."""
    dest_path = config['backup']['destination']['path']
    keep_daily = config['backup']['retention']['daily']
    keep_weekly = config['backup']['retention']['weekly']
    keep_monthly = config['backup']['retention']['monthly']

    logger.info(f"Applying retention policy to {dest_path}...")
    logger.info(f"Keeping: Daily={keep_daily}, Weekly={keep_weekly}, Monthly={keep_monthly}")

    try:
        backup_files = sorted(glob.glob(os.path.join(dest_path, BACKUP_FILENAME_PATTERN)), reverse=True)
        if not backup_files:
            logger.info("No existing backups found.")
            return

        daily_kept = 0
        weekly_kept = 0
        monthly_kept = 0
        to_delete = []
        last_weekly_date = None
        last_monthly_date = None

        for file_path in backup_files:
            filename = os.path.basename(file_path)
            match = re.match(r"vaultwarden-data-(\d{8}T\d{6})\.tar\.gz(\.gpg)?", filename)
            if not match:
                logger.warning(f"Skipping unrecognized file in destination: {filename}")
                continue

            timestamp_str = match.group(1)
            try:
                backup_date = datetime.strptime(timestamp_str, TIMESTAMP_FORMAT)
            except ValueError:
                logger.warning(f"Skipping file with invalid timestamp format: {filename}")
                continue

            is_weekly = backup_date.weekday() == 6
            is_monthly = backup_date.day == 1
            keep = False

            current_monthly_date = backup_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            if is_monthly and monthly_kept < keep_monthly and current_monthly_date != last_monthly_date:
                logger.debug(f"Keeping monthly: {filename}")
                keep = True
                monthly_kept += 1
                last_monthly_date = current_monthly_date

            current_weekly_date = backup_date.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=backup_date.weekday())
            if not keep and is_weekly and weekly_kept < keep_weekly and current_weekly_date != last_weekly_date:
                 logger.debug(f"Keeping weekly: {filename}")
                 keep = True
                 weekly_kept += 1
                 last_weekly_date = current_weekly_date

            if not keep and daily_kept < keep_daily:
                logger.debug(f"Keeping daily: {filename}")
                keep = True
                daily_kept += 1

            if not keep:
                to_delete.append(file_path)

        if to_delete:
            logger.info(f"Found {len(to_delete)} backups to delete based on retention policy.")
            for file_path in to_delete:
                try:
                    os.remove(file_path)
                    logger.info(f"Deleted old backup: {os.path.basename(file_path)}")
                except OSError as e:
                    logger.error(f"Failed to delete backup {os.path.basename(file_path)}: {e}")
        else:
            logger.info("No backups needed deletion according to retention policy.")

    except Exception as e:
        logger.error(f"Error applying retention policy: {e}")

# --- Command Functions ---

def backup(config):
    """Performs the backup process for Vaultwarden."""
    try:
        logger.info("--- Starting Vaultwarden Backup ---")
        start_time = datetime.now()

        if not manage_vaultwarden_container(config, "stop"):
            logger.error("Skipping backup run because container stop failed.")
            manage_vaultwarden_container(config, "start")
            return

        timestamp_str = start_time.strftime(TIMESTAMP_FORMAT)
        final_backup_path = None
        try:
            final_backup_path = create_backup_archive(config, timestamp_str)
            logger.info(f"Successfully created backup: {final_backup_path}")
        except Exception as e:
            logger.critical(f"Backup archive creation failed: {e}. Aborting backup run.")
            manage_vaultwarden_container(config, "start")
            return

        manage_vaultwarden_container(config, "start")

        if final_backup_path:
            apply_retention_policy(config)

        end_time = datetime.now()
        logger.info(f"--- Vaultwarden Backup Finished ---")
        logger.info(f"Duration: {end_time - start_time}")

    except Exception as e:
        logger.exception(f"An unexpected error occurred during the scheduled backup run: {e}")
        try:
            manage_vaultwarden_container(config, "start")
        except Exception as restart_e:
             logger.error(f"Failed to ensure Vaultwarden container was started after backup error: {restart_e}")

def restore(config, backup_id, target_dir_override, force_yes):
    """Performs the restore process for Vaultwarden."""
    config['_internal_mode'] = 'restore'

    logger.warning("--- Starting Vaultwarden Restore ---")
    logger.warning("!!! THIS IS A DESTRUCTIVE OPERATION !!!")
    start_time = datetime.now()

    vw_cfg = config['vaultwarden']
    backup_cfg = config['backup']
    target_data_dir = target_dir_override if target_dir_override else vw_cfg['data_dir']
    logger.info(f"Target data directory for restore: {target_data_dir}")

    target_parent_dir = os.path.dirname(target_data_dir)
    if not os.path.isdir(target_parent_dir):
        logger.critical(f"Parent directory of target does not exist: {target_parent_dir}")
        sys.exit(1)

    restore_temp_dir = backup_cfg['restore']['temp_dir']
    dest_path = backup_cfg['destination']['path']
    dest_type = backup_cfg['destination']['type']
    encrypt = backup_cfg.get('encryption', {}).get('enabled', False)
    restore_uid = backup_cfg['restore'].get('owner_uid')
    restore_gid = backup_cfg['restore'].get('owner_gid')

    logger.info(f"Searching for backup '{backup_id}' in {dest_path}...")
    backup_file_to_restore = None
    try:
        if dest_type != 'local':
             raise NotImplementedError(f"Restore from destination type '{dest_type}' is not implemented.")
        all_backups = sorted(glob.glob(os.path.join(dest_path, BACKUP_FILENAME_PATTERN)), reverse=True)
        if not all_backups:
            raise FileNotFoundError("No backup files found in destination.")

        if backup_id == 'latest':
            backup_file_to_restore = all_backups[0]
        else:
            for backup_path in all_backups:
                 if backup_id in os.path.basename(backup_path):
                      backup_file_to_restore = backup_path
                      break
            if not backup_file_to_restore:
                 raise FileNotFoundError(f"Backup with ID '{backup_id}' not found.")

        logger.info(f"Found backup to restore: {os.path.basename(backup_file_to_restore)}")

    except Exception as e:
        logger.critical(f"Failed to find backup: {e}")
        sys.exit(1)

    try:
        if os.path.exists(restore_temp_dir):
            shutil.rmtree(restore_temp_dir)
        os.makedirs(restore_temp_dir, exist_ok=True)
        logger.info(f"Created temporary directory: {restore_temp_dir}")
    except OSError as e:
        logger.critical(f"Failed to create temporary directory {restore_temp_dir}: {e}")
        sys.exit(1)

    local_archive_path_encrypted = os.path.join(restore_temp_dir, os.path.basename(backup_file_to_restore))
    local_archive_path_decrypted = local_archive_path_encrypted.replace('.gpg', '') if local_archive_path_encrypted.endswith('.gpg') else local_archive_path_encrypted
    is_encrypted_backup = local_archive_path_encrypted.endswith('.gpg')

    try:
        logger.info(f"Fetching backup '{os.path.basename(backup_file_to_restore)}' to temporary location...")
        if dest_type == 'local':
             shutil.copy2(backup_file_to_restore, local_archive_path_encrypted)
        else:
             raise NotImplementedError(f"Fetch from '{dest_type}' not implemented.")
        logger.info(f"Backup fetched to: {local_archive_path_encrypted}")

        if is_encrypted_backup:
            if not encrypt:
                 logger.warning("Backup file appears encrypted (.gpg), but encryption is not enabled in current config. Attempting decryption anyway.")
            logger.info(f"Decrypting {os.path.basename(local_archive_path_encrypted)}...")
            gpg_command = [
                'gpg', '--decrypt', '--output', local_archive_path_decrypted,
                local_archive_path_encrypted
            ]
            run_command(gpg_command)
            logger.info(f"Decryption complete: {os.path.basename(local_archive_path_decrypted)}")

    except Exception as e:
         logger.critical(f"Failed during fetch or decrypt: {e}")
         shutil.rmtree(restore_temp_dir)
         sys.exit(1)

    if not manage_vaultwarden_container(config, "stop"):
        pass

    if not force_yes and os.path.exists(target_data_dir):
        confirm = input(f"WARNING: Target data directory '{target_data_dir}' exists.\n"
                        f"This operation will DELETE IT and replace it with the contents of the backup.\n"
                        f"Proceed? (y/N): ")
        if confirm.lower() != 'y':
            logger.warning("Restore aborted by user.")
            manage_vaultwarden_container(config, "start")
            shutil.rmtree(restore_temp_dir)
            sys.exit(0)
        logger.info("User confirmed deletion of existing data.")
    elif os.path.exists(target_data_dir):
        logger.warning(f"Target data directory '{target_data_dir}' exists. Deleting due to --yes flag.")

    try:
        if os.path.exists(target_data_dir):
            logger.info(f"Deleting existing directory: {target_data_dir}")
            shutil.rmtree(target_data_dir)

        extract_parent_dir = os.path.dirname(target_data_dir)
        logger.info(f"Extracting '{os.path.basename(local_archive_path_decrypted)}' to {extract_parent_dir}...")
        shutil.unpack_archive(local_archive_path_decrypted, extract_parent_dir)
        logger.info("Extraction complete.")

        if not os.path.isdir(target_data_dir):
             raise RuntimeError(f"Extraction did not create the expected directory: {target_data_dir}")

    except Exception as e:
        logger.critical(f"Failed to replace data: {e}")
        logger.critical("The Vaultwarden data directory may be in an inconsistent state!")
        shutil.rmtree(restore_temp_dir)
        sys.exit(1)

    abs_target_data_dir = os.path.abspath(target_data_dir)
    if restore_uid is not None and restore_gid is not None:
        logger.info(f"Setting ownership of {abs_target_data_dir} to {restore_uid}:{restore_gid}")
        try:
             for root, dirs, files in os.walk(abs_target_data_dir):
                 for d in dirs:
                     os.chown(os.path.join(root, d), restore_uid, restore_gid)
                 for f in files:
                     os.chown(os.path.join(root, f), restore_uid, restore_gid)
             os.chown(abs_target_data_dir, restore_uid, restore_gid)

             logger.info(f"Setting permissions within {abs_target_data_dir}...")
             os.chmod(abs_target_data_dir, 0o700)
             for root, dirs, files in os.walk(abs_target_data_dir):
                 for d in dirs:
                     os.chmod(os.path.join(root, d), 0o700)
                 for f in files:
                     try:
                        os.chmod(os.path.join(root, f), 0o600)
                     except OSError as pe:
                         logger.warning(f"Could not set permissions on file {os.path.join(root, f)}: {pe}")

             logger.info("Ownership and permissions set successfully.")
        except Exception as e:
             logger.error(f"Failed to set ownership/permissions on {abs_target_data_dir}: {e}")
             logger.error("This likely requires running the script with sudo.")
             logger.warning("Continuing restore, but Vaultwarden might fail to start if permissions are incorrect.")

    try:
        manage_vaultwarden_container(config, "start")
    except Exception as e:
         logger.critical(f"Failed during Vaultwarden container start: {e}")
         logger.critical("Vaultwarden might not be running correctly.")
         shutil.rmtree(restore_temp_dir)
         sys.exit(1)

    try:
        logger.info(f"Cleaning up temporary directory: {restore_temp_dir}")
        shutil.rmtree(restore_temp_dir)
    except OSError as e:
        logger.warning(f"Could not clean up temporary directory {restore_temp_dir}: {e}")

    config.pop('_internal_mode', None)

    end_time = datetime.now()
    logger.info(f"--- Vaultwarden Restore Finished ---")
    logger.info(f"Duration: {end_time - start_time}")
    logger.info("Please verify Vaultwarden functionality.")

def run_scheduler(config):
    """Runs the backup function on a schedule."""
    interval = config['backup']['schedule']['interval_minutes']
    logger.info(f"Starting scheduler. Backup interval: {interval} minutes.")

    schedule.every(interval).minutes.do(backup, config=config)

    logger.info("Running initial backup job at startup...")
    schedule.run_all()

    logger.info("Scheduler started. Waiting for next scheduled run...")
    while True:
        schedule.run_pending()
        time.sleep(60)

# --- Main Execution ---
def main():
    global file_handler

    parser = argparse.ArgumentParser(description="Manage Vaultwarden Docker container backups, restores, and scheduling.")
    parser.add_argument('command', choices=['backup', 'restore', 'run-scheduler'], help="The command to execute (backup, restore, or run-scheduler for continuous backups).")
    parser.add_argument('--config', required=True, help="Path to the YAML configuration file (e.g., config.yaml).")
    parser.add_argument('--log-file', default=DEFAULT_LOG_FILE, help=f"Path to the log file (default: {DEFAULT_LOG_FILE}).")
    parser.add_argument('-v', '--verbose', action='store_true', help="Enable verbose (DEBUG) logging.")

    restore_group = parser.add_argument_group('restore options')
    restore_group.add_argument('--backup-id', help="Timestamp ID of the backup to restore (e.g., '20230115T103000') or 'latest'. Required for restore.")
    restore_group.add_argument('--target-dir', help="Override the Vaultwarden host data directory path for restore. Defaults to data_dir in config.")
    restore_group.add_argument('--yes', action='store_true', help="Bypass confirmation prompt during restore (DANGEROUS!).")

    args = parser.parse_args()

    try:
        log_dir = os.path.dirname(args.log_file)
        if log_dir and not os.path.exists(log_dir):
             os.makedirs(log_dir)
        file_handler = logging.FileHandler(args.log_file)
        file_handler.setFormatter(log_formatter)
        logger.addHandler(file_handler)
    except Exception as e:
         logger.error(f"Failed to configure file logging to {args.log_file}: {e}")

    if args.verbose:
        logger.setLevel(logging.DEBUG)
        logger.debug("Verbose logging enabled.")

    logger.info(f"Executing command: {args.command}")

    config = load_config(args.config)

    if args.command == 'backup':
        backup(config)
    elif args.command == 'restore':
        if not args.backup_id:
            parser.error("--backup-id is required for the restore command.")
        restore(config, args.backup_id, args.target_dir, args.yes)
    elif args.command == 'run-scheduler':
        run_scheduler(config)
    else:
        logger.error(f"Unknown command: {args.command}")
        sys.exit(1)

if __name__ == "__main__":
    main() 