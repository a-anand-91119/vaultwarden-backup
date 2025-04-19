import argparse
import logging
import sys
import os

from .manager import VaultwardenBackupManager
from .config_loader import ConfigError

DEFAULT_LOG_FILE = "vaultwarden_manager.log"

log_formatter = logging.Formatter('%(asctime)s - %(levelname)s [%(name)s] - %(message)s')
logger = logging.getLogger(__package__)

stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(log_formatter)
logger.addHandler(stream_handler)

file_handler = None


def main():
    global file_handler

    parser = argparse.ArgumentParser(
        prog="Vault warden Backup Manager",
        description="Manage Vault warden Docker container backups, restores, and scheduling."
    )
    parser.add_argument('command', choices=['backup', 'restore', 'run-scheduler'], help="The command to execute.")
    parser.add_argument('--config', required=True, help="Path to the YAML configuration file.")
    parser.add_argument('--log-file', default=DEFAULT_LOG_FILE,
                        help=f"Path to the log file (default: {DEFAULT_LOG_FILE}).")
    parser.add_argument('-v', '--verbose', action='store_true', help="Enable verbose (DEBUG) logging.")

    restore_group = parser.add_argument_group('restore options')
    restore_group.add_argument('--backup-id', help="Timestamp ID or 'latest'. Required for restore.")
    restore_group.add_argument('--target-dir', help="Override Vaultwarden host data directory path for restore.")
    restore_group.add_argument('--yes', action='store_true',
                               help="Bypass confirmation prompt during restore (DANGEROUS!).")

    args = parser.parse_args()
    setup_logging(args)

    try:
        manager: VaultwardenBackupManager = VaultwardenBackupManager(args.config)

        logger.info(f"Executing command: {args.command}")
        if args.command == 'backup':
            manager.backup()
        elif args.command == 'restore':
            if not args.backup_id:
                parser.error("--backup-id is required for the restore command.")
            manager.restore(args.backup_id, args.target_dir, args.yes)
        elif args.command == 'run-scheduler':
            manager.run_scheduler()
        else:
            logger.error(f"Unknown command: {args.command}")

    except ConfigError as e:
        logger.critical(f"Invalid config provided: {e}")
    except FileNotFoundError as e:
        # Specific file not found errors (e.g., backup ID, data dir)
        logger.critical(f"File not found error: {e}")
    except NotImplementedError as e:
        logger.critical(f"Feature not implemented: {e}")
    except Exception as e:
        logger.critical(f"An unexpected critical error occurred: {e}", exc_info=True)
    sys.exit(1)


def setup_logging(args):
    global file_handler
    try:
        log_dir = os.path.dirname(args.log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)

        file_handler = logging.FileHandler(args.log_file)
        file_handler.setFormatter(log_formatter)
        logger.addHandler(file_handler)

        if args.verbose:
            logging.getLogger(__package__).setLevel(logging.DEBUG)
            logger.debug("Verbose logging enabled.")
        else:
            logging.getLogger(__package__).setLevel(logging.INFO)

    except Exception as e:
        logger.error(f"Failed to configure file logging to {args.log_file}: {e}")


if __name__ == "__main__":
    main()
