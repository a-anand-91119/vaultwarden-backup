import os
import sys
import yaml
import logging

logger = logging.getLogger(__name__)

class ConfigError(Exception):
    """Custom exception for configuration errors."""
    pass

class ConfigLoader:
    """Loads and validates the YAML configuration file."""

    def __init__(self, config_path):
        self.config_path = config_path
        self.config = self._load_and_validate()

    def get_config(self):
        return self.config

    def _load_and_validate(self):
        if not os.path.exists(self.config_path):
            raise ConfigError(f"Configuration file not found: {self.config_path}")
        try:
            with open(self.config_path, 'r') as f:
                config = yaml.safe_load(f)

            # --- Validation ---
            if not isinstance(config, dict):
                 raise ConfigError("Config file is not a valid YAML dictionary.")

            required_sections = ['vaultwarden', 'backup']
            for section in required_sections:
                if section not in config or not isinstance(config[section], dict):
                    raise ConfigError(f"Missing or invalid '{section}' section in config.")

            # Vaultwarden validation
            vw_cfg = config['vaultwarden']
            if not vw_cfg.get('container_name') or not isinstance(vw_cfg['container_name'], str):
                raise ConfigError("Missing or invalid 'container_name' (string) in 'vaultwarden' section.")
            if not vw_cfg.get('data_dir') or not isinstance(vw_cfg['data_dir'], str):
                 raise ConfigError("Missing or invalid 'data_dir' (string) in 'vaultwarden' section.")

            # Validate skip_start_stop (optional, defaults to False)
            skip_start_stop = vw_cfg.get('skip_start_stop', False) # Get value or default
            if not isinstance(skip_start_stop, bool):
                raise ConfigError("Invalid type for 'skip_start_stop' in 'vaultwarden' section. Expected a boolean (true/false).")
            # Ensure the value in the config dict is the potentially defaulted value
            vw_cfg['skip_start_stop'] = skip_start_stop

            # Backup validation
            backup_cfg = config['backup']
            required_backup_keys = ['schedule', 'destination', 'retention', 'restore']
            for key in required_backup_keys:
                if key not in backup_cfg or not isinstance(backup_cfg[key], dict):
                     raise ConfigError(f"Missing or invalid '{key}' subsection in 'backup' section.")

            # Schedule validation
            schedule_cfg = backup_cfg['schedule']
            interval = schedule_cfg.get('interval_minutes')
            if not isinstance(interval, int) or interval <= 0:
                 raise ConfigError("Missing or invalid 'interval_minutes' (positive integer) in 'backup.schedule' section.")

            # Destination validation
            dest_cfg = backup_cfg['destination']
            if not dest_cfg.get('type') or not isinstance(dest_cfg['type'], str):
                raise ConfigError("Missing or invalid 'type' (string) in 'backup.destination' section.")
            if not dest_cfg.get('path') or not isinstance(dest_cfg['path'], str):
                raise ConfigError("Missing or invalid 'path' (string) in 'backup.destination' section.")
            if dest_cfg['type'] != 'local':
                 logger.warning(f"Destination type '{dest_cfg['type']}' is not yet fully supported.")

            # Retention validation
            ret_cfg = backup_cfg['retention']
            ret_keys = ['daily', 'weekly', 'monthly']
            for key in ret_keys:
                val = ret_cfg.get(key)
                if not isinstance(val, int) or val < 0:
                     raise ConfigError(f"Invalid or missing '{key}' value in 'backup.retention'. Must be a non-negative integer.")

            # Restore validation
            restore_cfg = backup_cfg['restore']
            if not restore_cfg.get('temp_dir') or not isinstance(restore_cfg['temp_dir'], str):
                raise ConfigError("Missing or invalid 'temp_dir' (string) in 'backup.restore' section.")
            uid = restore_cfg.get('owner_uid')
            gid = restore_cfg.get('owner_gid')
            if uid is not None and not isinstance(uid, int):
                raise ConfigError("Invalid type for 'owner_uid' in 'backup.restore'. Expected an integer or null/omitted.")
            if gid is not None and not isinstance(gid, int):
                 raise ConfigError("Invalid type for 'owner_gid' in 'backup.restore'. Expected an integer or null/omitted.")

            # Encryption validation
            enc_cfg = backup_cfg.get('encryption', {}) # Defaults to empty dict if section missing
            if enc_cfg.get('enabled', False):
                if not enc_cfg.get('gpg_key_id') or not isinstance(enc_cfg['gpg_key_id'], str):
                     raise ConfigError("Missing or invalid 'gpg_key_id' (string) in 'backup.encryption' when 'enabled' is true.")

            return config
        except (yaml.YAMLError, ValueError, KeyError, TypeError, ConfigError) as e:
            # Log the specific error and re-raise as ConfigError
            logger.error(f"Configuration error in '{self.config_path}': {e}")
            raise ConfigError(f"Invalid configuration: {e}") 