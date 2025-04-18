import argparse
import logging
import sys
import os

# Relative imports for running as a module
from .manager import VaultwardenBackupManager
from .config_loader import ConfigError

# Constants from the old script, maybe move to a constants module later
DEFAULT_LOG_FILE = "vaultwarden_manager.log"

# Logging setup (similar to before, but using __package__)
log_formatter = logging.Formatter('%(asctime)s - %(levelname)s [%(name)s] - %(message)s')
logger = logging.getLogger(__package__) # Use package name for root logger

# Console Handler
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(log_formatter)
logger.addHandler(stream_handler)

# File Handler
file_handler = None

def main():
    global file_handler

    parser = argparse.ArgumentParser(
        prog="vaultwarden_backup_manager",
        description="Manage Vaultwarden Docker container backups, restores, and scheduling."
    )
    parser.add_argument('command', choices=['backup', 'restore', 'run-scheduler'], help="The command to execute.")
    parser.add_argument('--config', required=True, help="Path to the YAML configuration file.")
    parser.add_argument('--log-file', default=DEFAULT_LOG_FILE, help=f"Path to the log file (default: {DEFAULT_LOG_FILE}).")
    parser.add_argument('-v', '--verbose', action='store_true', help="Enable verbose (DEBUG) logging.")

    restore_group = parser.add_argument_group('restore options')
    restore_group.add_argument('--backup-id', help="Timestamp ID or 'latest'. Required for restore.")
    restore_group.add_argument('--target-dir', help="Override Vaultwarden host data directory path for restore.")
    restore_group.add_argument('--yes', action='store_true', help="Bypass confirmation prompt during restore (DANGEROUS!).")

    args = parser.parse_args()

    # --- Setup File Logging ---
    try:
        log_dir = os.path.dirname(args.log_file)
        if log_dir and not os.path.exists(log_dir):
             os.makedirs(log_dir)
        file_handler = logging.FileHandler(args.log_file)
        file_handler.setFormatter(log_formatter)
        # Add handler to the package logger
        logger.addHandler(file_handler)

        # Set root logger level based on verbose flag
        # This affects all loggers within the package
        if args.verbose:
            logging.getLogger(__package__).setLevel(logging.DEBUG)
            logger.debug("Verbose logging enabled.")
        else:
            logging.getLogger(__package__).setLevel(logging.INFO)

    except Exception as e:
         # Log to console if file logging fails
         logger.error(f"Failed to configure file logging to {args.log_file}: {e}")

    # --- Initialize Manager and Run Command ---
    try:
        # Pass config path, manager handles loading
        manager = VaultwardenBackupManager(args.config)

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
            sys.exit(1)

    except ConfigError:
        # Config errors are logged by the loader, exit cleanly
        sys.exit(1)
    except FileNotFoundError as e:
        # Specific file not found errors (e.g., backup ID, data dir)
        logger.critical(f"File not found error: {e}")
        sys.exit(1)
    except NotImplementedError as e:
        logger.critical(f"Feature not implemented: {e}")
        sys.exit(1)
    except Exception as e:
        # Catch any other unexpected errors
        logger.critical(f"An unexpected critical error occurred: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main() 