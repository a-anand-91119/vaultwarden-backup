import os
import glob
import re
import shutil
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Define constants within the module
TIMESTAMP_FORMAT = "%Y%m%dT%H%M%S"
BACKUP_FILENAME_PATTERN = "vaultwarden-data-*.tar.gz*"


class BackupStore:
    """Manages the backup storage location (currently local)."""

    def __init__(self, config):
        self.config = config
        # Currently only supports 'local' destination type
        dest_config = config.get('backup', {}).get('destination', {})
        self.dest_type = dest_config.get('type')
        self.dest_path = dest_config.get('path')
        self.retention_config = config.get('backup', {}).get('retention', {})

        if self.dest_type != 'local':
            logger.warning(
                f"Destination type '{self.dest_type}' is not fully supported. Only local operations available.")
        if not self.dest_path:
            raise ValueError("Backup destination path is not configured.")

    def list_backups(self):
        """Returns a sorted list of backup file paths (newest first)."""
        if self.dest_type != 'local':
            return []  # Only support local listing for now
        try:
            backup_files = sorted(glob.glob(os.path.join(self.dest_path, BACKUP_FILENAME_PATTERN)), reverse=True)
            return backup_files
        except Exception as e:
            logger.error(f"Error listing backups in {self.dest_path}: {e}")
            return []

    def apply_retention(self):
        """Deletes old backups based on the retention policy."""
        if self.dest_type != 'local':
            logger.warning("Retention policy skipped: Only supported for local destination type.")
            return

        keep_daily = self.retention_config.get('daily', 7)
        keep_weekly = self.retention_config.get('weekly', 4)
        keep_monthly = self.retention_config.get('monthly', 6)

        logger.info(f"Applying retention policy to {self.dest_path}...")
        logger.info(f"Keeping: Daily={keep_daily}, Weekly={keep_weekly}, Monthly={keep_monthly}")

        try:
            backup_files = self.list_backups()
            if not backup_files:
                logger.info("No existing backups found.")
                return

            daily_kept = 0
            weekly_kept = 0
            monthly_kept = 0
            to_keep = set()
            kept_weekly_dates = set()  # Track dates of kept weekly backups
            kept_monthly_dates = set()  # Track dates of kept monthly backups
            parsed_backup_files = {}  # Store parsed date for valid backup files

            for file_path in backup_files:
                filename = os.path.basename(file_path)
                match = re.match(r"vaultwarden-data-(\d{8}T\d{6})\.tar\.gz(\.gpg)?", filename)
                if not match:
                    logger.warning(f"Skipping unrecognized file in destination: {filename}")
                    continue

                timestamp_str = match.group(1)
                try:
                    backup_date = datetime.strptime(timestamp_str, TIMESTAMP_FORMAT)
                    parsed_backup_files[file_path] = backup_date  # Store parsed date
                except ValueError:
                    logger.warning(f"Skipping file with invalid timestamp format: {filename}")
                    continue

            # Sort by date descending for retention logic
            sorted_parsed_files = sorted(parsed_backup_files.items(), key=lambda item: item[1], reverse=True)

            for file_path, backup_date in sorted_parsed_files:
                filename = os.path.basename(file_path)  # Get filename again for logging
                # Determine type, prioritizing Monthly
                is_monthly = backup_date.day == 1
                is_weekly = not is_monthly and backup_date.weekday() == 6  # Sunday, but only if not the 1st
                keep = False

                # Keep Monthly
                current_monthly_date = backup_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                if is_monthly and monthly_kept < keep_monthly:
                    # Check if this month has already been kept
                    if current_monthly_date not in kept_monthly_dates:
                        logger.debug(f"Keeping monthly: {filename}")
                        keep = True
                        monthly_kept += 1
                        kept_monthly_dates.add(current_monthly_date)

                # Keep Weekly (only if not already kept as monthly)
                # Calculate the start of the week (Monday) for this backup's date
                current_week_start_date = backup_date.date() - timedelta(days=backup_date.weekday())
                if not keep and is_weekly and weekly_kept < keep_weekly:  # is_weekly check now incorporates the not is_monthly logic
                    # Check if this week has already been kept
                    if current_week_start_date not in kept_weekly_dates:
                        logger.debug(f"Keeping weekly: {filename} (Week starting: {current_week_start_date})")
                        keep = True
                        weekly_kept += 1
                        kept_weekly_dates.add(current_week_start_date)

                # Keep Daily (only if not already kept as monthly or weekly)
                is_daily_candidate = not keep  # Track if it *could* be kept as daily
                if is_daily_candidate and daily_kept < keep_daily:
                    logger.debug(f"Keeping daily: {filename}")
                    keep = True
                    # Increment counts only if successfully kept
                    daily_kept += 1

                if keep:
                    to_keep.add(file_path)

            # Now delete anything from the *parsed* list that is not in the to_keep set
            to_delete = [file_path for file_path in parsed_backup_files if file_path not in to_keep]

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

    def find_backup(self, backup_id):
        """Finds a specific backup file path by ID or 'latest'."""
        if self.dest_type != 'local':
            raise NotImplementedError("Finding backups is only supported for local destination type.")

        all_backups = self.list_backups()
        if not all_backups:
            raise FileNotFoundError("No backup files found in destination.")

        if backup_id == 'latest':
            return all_backups[0]
        else:
            for backup_path in all_backups:
                if backup_id in os.path.basename(backup_path):
                    return backup_path
            raise FileNotFoundError(f"Backup with ID '{backup_id}' not found.")

    def fetch_backup_local(self, source_path, destination_path):
        """Copies a backup file locally."""
        if self.dest_type != 'local':
            raise NotImplementedError("Fetching backups is only supported for local destination type.")

        logger.info(f"Fetching backup '{os.path.basename(source_path)}' to {destination_path}...")
        try:
            shutil.copy2(source_path, destination_path)
            logger.info(f"Backup fetched.")
        except Exception as e:
            logger.error(f"Failed to fetch local backup: {e}")
            raise
