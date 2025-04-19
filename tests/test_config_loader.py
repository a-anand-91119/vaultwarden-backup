import pytest
import yaml
from pathlib import Path
import re  # Import re for regex matching

# Adjust import based on project structure (running pytest from root)
from vaultwarden_backup_manager.config_loader import ConfigLoader, ConfigError

# Minimal valid config data
VALID_CONFIG_MINIMAL = {
    'vaultwarden': {
        'container_name': 'vw-test',
        'data_dir': '/data',
        'skip_start_stop': False
    },
    'backup': {
        'schedule': {'interval_minutes': 1440},
        'destination': {'type': 'local', 'path': '/backups'},
        'retention': {'daily': 7, 'weekly': 4, 'monthly': 6},
        'restore': {'temp_dir': '/tmp/restore'}
    }
}

# More complete valid config data
VALID_CONFIG_FULL = {
    'vaultwarden': {
        'container_name': 'vw-test-full',
        'data_dir': '/data/full',
        'skip_start_stop': False
    },
    'backup': {
        'schedule': {'interval_minutes': 60},
        'destination': {'type': 'local', 'path': '/backup/storage'},
        'encryption': {'enabled': True, 'gpg_key_id': 'test@example.com'},
        'retention': {'daily': 10, 'weekly': 5, 'monthly': 12},
        'restore': {'temp_dir': '/tmp/vw-restore', 'owner_uid': 1000, 'owner_gid': 1001}
    },
    'notifications': {  # Optional section
        'enabled': False
    }
}


@pytest.fixture
def create_config_file(tmp_path: Path):
    """Pytest fixture to create a temporary config file."""

    def _create_file(content_dict, filename="config.yaml"):
        file_path = tmp_path / filename
        # Ensure parent directory exists if filename includes subdir
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, 'w') as f:
            yaml.dump(content_dict, f)
        return file_path

    return _create_file


# --- Success Cases ---

def test_load_valid_minimal_config(create_config_file):
    """Tests loading a valid minimal configuration."""
    config_path = create_config_file(VALID_CONFIG_MINIMAL)
    loader = ConfigLoader(str(config_path))
    loaded_config = loader.get_config()
    assert loaded_config == VALID_CONFIG_MINIMAL


def test_load_valid_full_config(create_config_file):
    """Tests loading a valid configuration with optional fields."""
    config_path = create_config_file(VALID_CONFIG_FULL)
    loader = ConfigLoader(str(config_path))
    loaded_config = loader.get_config()
    assert loaded_config == VALID_CONFIG_FULL


# --- Failure Cases ---

def test_load_non_existent_file():
    """Tests loading a non-existent config file."""
    with pytest.raises(ConfigError, match="Configuration file not found"):
        ConfigLoader("/non/existent/path/config.yaml")


def test_load_invalid_yaml(create_config_file):
    """Tests loading a file that is not valid YAML."""
    file_path = create_config_file(None, filename="invalid.yaml")  # Create empty file first
    with open(file_path, 'w') as f:
        f.write("invalid yaml: [")  # Write invalid content
    # Match the re-raised exception format, looking for ParserError details
    match_pattern = re.escape("Invalid configuration: while parsing a flow node")  # Start of ParserError msg
    with pytest.raises(ConfigError, match=match_pattern):
        ConfigLoader(str(file_path))


@pytest.mark.parametrize(
    "missing_key_path_str",  # Use string representation for parameter name clarity
    [
        "vaultwarden",
        "backup",
        "vaultwarden.container_name",
        "vaultwarden.data_dir",
        "backup.schedule",
        "backup.schedule.interval_minutes",
        "backup.destination",
        "backup.destination.type",
        "backup.destination.path",
        "backup.retention",
        "backup.retention.daily",
        "backup.retention.weekly",
        "backup.retention.monthly",
        "backup.restore",
        "backup.restore.temp_dir",
    ]
)
def test_missing_required_keys(create_config_file, missing_key_path_str):
    """Tests missing various required keys or sections."""
    config = yaml.safe_load(yaml.dump(VALID_CONFIG_MINIMAL))  # Deep copy
    keys = missing_key_path_str.split(".")

    # Navigate dictionary and delete the target key
    d = config
    for key in keys[:-1]:
        d = d[key]
    del d[keys[-1]]

    config_path = create_config_file(config)
    # Use regex to match the expected pattern, allowing for variations in quotes/exact wording
    # Match should start with "Invalid configuration: Missing or invalid..."
    # Special handling for retention keys because the error message is more specific
    if missing_key_path_str.startswith("backup.retention.") and len(keys) == 3:
        match_pattern = re.escape(
            f"Invalid configuration: Invalid or missing '{keys[-1]}' value in 'backup.retention'. Must be a non-negative integer.")
    else:
        match_pattern = re.escape(f"Invalid configuration: Missing or invalid '{keys[-1]}'")
    with pytest.raises(ConfigError, match=match_pattern):
        ConfigLoader(str(config_path))


@pytest.mark.parametrize(
    "invalid_path_str, invalid_value, match_str",  # Use string for path
    [
        ("vaultwarden.container_name", 123, "Missing or invalid 'container_name' (string)"),
        ("vaultwarden.data_dir", None, "Missing or invalid 'data_dir' (string)"),
        ("backup.schedule.interval_minutes", "abc", "Missing or invalid 'interval_minutes' (positive integer)"),
        ("backup.schedule.interval_minutes", 0, "Missing or invalid 'interval_minutes' (positive integer)"),
        ("backup.schedule.interval_minutes", -10, "Missing or invalid 'interval_minutes' (positive integer)"),
        ("backup.destination.type", True, "Missing or invalid 'type' (string)"),
        ("backup.destination.path", 123.45, "Missing or invalid 'path' (string)"),
        ("backup.retention.daily", -1, "Invalid or missing 'daily' value"),
        ("backup.retention.weekly", "many", "Invalid or missing 'weekly' value"),
        ("backup.retention.monthly", None, "Invalid or missing 'monthly' value"),
        ("backup.restore.temp_dir", [], "Missing or invalid 'temp_dir' (string)"),
        ("backup.restore.owner_uid", "1000", "Invalid type for 'owner_uid'"),
        ("backup.restore.owner_gid", 1000.5, "Invalid type for 'owner_gid'"),
    ]
)
def test_invalid_types(create_config_file, invalid_path_str, invalid_value, match_str):
    """Tests various invalid data types for config values."""
    config = yaml.safe_load(yaml.dump(VALID_CONFIG_FULL))  # Deep copy
    keys = invalid_path_str.split(".")

    # Navigate dictionary and set the invalid value
    d = config
    for key in keys[:-1]:
        d = d[key]
    d[keys[-1]] = invalid_value

    config_path = create_config_file(config)
    # Expect the error message to be wrapped by "Invalid configuration: ..."
    expected_regex = re.escape(f"Invalid configuration: {match_str}")
    with pytest.raises(ConfigError, match=expected_regex):
        ConfigLoader(str(config_path))


def test_encryption_enabled_no_key(create_config_file):
    """Tests config error when encryption is enabled but gpg_key_id is missing."""
    config = yaml.safe_load(yaml.dump(VALID_CONFIG_FULL))  # Deep copy
    config["backup"]["encryption"] = {"enabled": True}  # Missing key_id
    config_path = create_config_file(config)
    # Match the wrapped error message
    match_pattern = re.escape(
        "Invalid configuration: Missing or invalid 'gpg_key_id' (string) in 'backup.encryption' when 'enabled' is true.")
    with pytest.raises(ConfigError, match=match_pattern):
        ConfigLoader(str(config_path))


def test_encryption_enabled_invalid_key(create_config_file):
    """Tests config error when encryption is enabled but gpg_key_id is not a string."""
    config = yaml.safe_load(yaml.dump(VALID_CONFIG_FULL))  # Deep copy
    config["backup"]["encryption"] = {"enabled": True, "gpg_key_id": 12345}
    config_path = create_config_file(config)
    # Match the wrapped error message
    match_pattern = re.escape(
        "Invalid configuration: Missing or invalid 'gpg_key_id' (string) in 'backup.encryption' when 'enabled' is true.")
    with pytest.raises(ConfigError, match=match_pattern):
        ConfigLoader(str(config_path))


def test_encryption_disabled_no_key_ok(create_config_file):
    """Tests that it's okay to omit gpg_key_id if encryption is disabled or missing."""
    config = yaml.safe_load(yaml.dump(VALID_CONFIG_MINIMAL))  # Deep copy
    # Case 1: encryption section missing (implicitly disabled)
    config_path = create_config_file(config)
    loader = ConfigLoader(str(config_path))
    # The loader adds the default, so assert against the modified config
    expected_config_case1 = yaml.safe_load(yaml.dump(config)) # Deep copy
    expected_config_case1['vaultwarden']['skip_start_stop'] = False
    assert loader.get_config() == expected_config_case1

    # Case 2: encryption enabled: false, key missing
    config["backup"]["encryption"] = {"enabled": False}
    config_path_2 = create_config_file(config, filename="config2.yaml")
    loader_2 = ConfigLoader(str(config_path_2))
    # The loader adds the default, so assert against the modified config
    expected_config_case2 = yaml.safe_load(yaml.dump(config))
    expected_config_case2['vaultwarden']['skip_start_stop'] = False
    assert loader_2.get_config() == expected_config_case2
