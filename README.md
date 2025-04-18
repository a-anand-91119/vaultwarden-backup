# Vaultwarden Backup & Restore Manager

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/downloads/)

This Python tool provides automated backup and restore capabilities for a Vaultwarden Docker container installation.

**Project Links:**
*   **Homepage / Primary Repo:** [GitLab (Self-Hosted)](https://gitlab.notyouraverage.dev/a.anand.91119/vaultwarden-backup)
*   **GitHub Mirror:** [GitHub](https://github.com/a-anand-91119/vaultwarden-backup)
*   **GitLab.com Mirror:** [GitLab.com](https://gitlab.com/repo-syncer-managed-groups/vaultwarden-backup)

## Features

*   **Automated Backups:** Creates timestamped, compressed archives (`.tar.gz`) of the entire Vaultwarden data directory.
*   **Automated Restores:** Restores a specified backup to the target data directory.
*   **Encryption:** Optionally encrypts backups using GPG.
*   **Retention Policy:** Automatically deletes older backups based on configurable daily, weekly, and monthly retention settings.
*   **Configurable:** Uses a YAML file for configuration.
*   **Logging:** Logs operations to both console and a file.
*   **Container Management:** Stops and starts the specified Vaultwarden container during backup/restore for data consistency.

## Prerequisites

*   Python 3.8+ and `pip`
*   A running Vaultwarden instance in a Docker container.
*   Access to the Docker host machine.
*   The `docker` command-line tool installed and accessible.
*   Necessary command-line tools installed on the *host* where the script/container runs:
    *   `tar`, `gzip` (usually standard)
    *   `gpg` (if using encryption)
*   **Sudo privileges are likely required** for:
    *   Running `docker stop`/`start` commands via the Docker socket.
    *   The `restore` command if setting file ownership (`owner_uid`/`owner_gid` in config) or deleting existing data owned by another user when running the script directly on the host.

## Development Setup

If you want to modify or contribute to this tool:

1.  **Clone Repository:** `git clone <repository-url>`
2.  **Create Virtual Environment:**
    ```bash
    python -m venv .venv
    source .venv/bin/activate # On Linux/macOS
    # .\.venv\Scripts\activate # On Windows
    ```
3.  **Install in Editable Mode (with Test Dependencies):**
    This command installs the package such that changes in the `src` directory are immediately reflected, and includes `pytest` for running tests.
    ```bash
    pip install -e '.[test]'
    ```
4.  **Run Tests (Optional):**
    ```bash
    pytest
    ```

## Installation (Standard User)

If you just want to use the tool, you can install it directly using pip (once published or from a local clone):

```bash
# From local clone
pip install .

# From PyPI (if published)
# pip install vaultwarden-backup-manager
```

This will install the package and its runtime dependencies (`PyYAML`, `schedule`) and make the `vaultwarden-backup` command available in your environment (or the virtual environment if used).

## Configuration (`config.yaml`)

**Crucially, how you set paths in `config.yaml` depends on how you run the script:**

*   **Running Directly on Host (Using `python -m vaultwarden_backup_manager ...`):**
    *   `vaultwarden.data_dir`: Set to the *actual host path* of your Vaultwarden data (e.g., `/srv/vaultwarden/data`).
    *   `backup.destination.path`: Set to the *actual host path* for storing backups (e.g., `/mnt/backups/vaultwarden`).
    *   `backup.restore.temp_dir`: Set to a suitable *host path* for temporary files (e.g., `/tmp/vw_restore`).
*   **Running via Docker (`docker run` or `docker compose`):**
    *   `vaultwarden.data_dir`: MUST match the *target path* of the data volume mount (e.g., `/data`).
    *   `backup.destination.path`: MUST match the *target path* of the backup volume mount (e.g., `/backup`).
    *   `backup.restore.temp_dir`: Set to a path *inside the container* (e.g., `/tmp/vw_restore_temp`).
    *   The actual host paths are defined in the `volumes:` section of your `docker run` command or `docker-compose.yaml` file.

Copy `config.yaml.example` to `config.yaml` and edit it according to your setup and the path guidance above.

## Usage

Use the `vaultwarden-backup` command after installation, or `python -m vaultwarden_backup_manager` if running directly from the source checkout. Remember you might need `sudo` depending on your Docker permissions setup, especially when running directly on the host.

**Configuration File:** Always specify the configuration file using `--config`.

**Log File:** Logs are written to `vaultwarden_manager.log` by default. Change with `--log-file`.

**Verbose Logging:** Add `-v` or `--verbose` for DEBUG level logging.

### Backup (Manual)

Creates a backup according to the configuration.

```bash
# Run using installed command
sudo vaultwarden-backup backup --config /path/to/your/config.yaml

# Run directly from source checkout
# sudo python -m vaultwarden_backup_manager backup --config /path/to/your/config.yaml

# Run via Docker (using docker run for a one-off backup)
# Replace IMAGE_NAME and host paths as needed
sudo docker run --rm -it \\
  -v /var/run/docker.sock:/var/run/docker.sock \\
  -v /path/to/host/config.yaml:/config/config.yaml:ro \\
  -v /path/to/vaultwarden/host/data-directory:/data:ro \\
  -v /path/to/host/backup/storage:/backup \\
  registry.gitlab.notyouraverage.dev/a.anand.91119/vaultwarden-backup:latest \\
  backup --config /config/config.yaml
```

### Restore

Restores a specified backup.

**WARNING:** Destructive operation. Stops the container, deletes the target data directory (unless `--target-dir` specifies a new empty location), and restores the archive.
**SUDO:** Likely required when running directly on host.

```bash
# Run using installed command
# Restore latest backup, will prompt for confirmation
sudo vaultwarden-backup restore --config /path/to/your/config.yaml --backup-id latest

# Restore specific backup, skip confirmation (DANGEROUS)
sudo vaultwarden-backup restore --config /path/to/your/config.yaml --backup-id <TIMESTAMP_ID> --yes

# Run via Docker (using docker compose -f docker-compose.restore.yaml run)
# Make sure docker-compose.restore.yaml volume paths are correct!
docker compose -f docker-compose.restore.yaml run --rm restore \\
  restore --config /config/config.yaml --backup-id latest --target-dir /target/data_dir_name

# Run via Docker (using docker run)
# Replace IMAGE_NAME and host paths as needed
sudo docker run --rm -it \\
  -v /var/run/docker.sock:/var/run/docker.sock \\
  -v /path/to/host/config.yaml:/config/config.yaml:ro \\
  -v /path/to/host/backup/storage:/backup:ro \\
  -v /path/to/vaultwarden/host/parent-directory:/target \\
  registry.gitlab.notyouraverage.dev/a.anand.91119/vaultwarden-backup:latest \\
  restore --config /config/config.yaml --backup-id latest --target-dir /target/data_dir_name
```
*(Note: Replace `<TIMESTAMP_ID>`, `/target/data_dir_name`, image name, and host paths as needed)*

### Run Scheduler (Continuous Backups)

This command runs indefinitely in the foreground, triggering backups based on `backup.schedule.interval_minutes` in the config. This is the default command run by the Docker image.

```bash
# Run using installed command (runs in foreground)
sudo vaultwarden-backup run-scheduler --config /path/to/your/config.yaml

# Run via Docker (using docker-compose.yaml - recommended)
# Assumes docker-compose.yaml points to the correct image and host paths
docker compose up -d backup

# Run via Docker (using docker run)
# Replace IMAGE_NAME and host paths as needed
sudo docker run -d \\
  --name vaultwarden-backup \\
  --restart=unless-stopped \\
  -e VERBOSE_LOGGING="false"   # Optional \\
  -e TZ="Asia/Kolkata"         # Optional: Set your timezone \\
  -v /var/run/docker.sock:/var/run/docker.sock \\
  -v /path/to/host/config.yaml:/config/config.yaml:ro \\
  -v /path/to/vaultwarden/host/data-directory:/data:ro \\
  -v /path/to/host/backup/storage:/backup \\
  registry.gitlab.notyouraverage.dev/a.anand.91119/vaultwarden-backup:latest
  # No command needed here; the image's default CMD runs the scheduler
```

## Automation (Scheduling Backups)

If running the script directly on the host (not via Docker), you can use `cron` to run the `vaultwarden-backup backup` command periodically.

Example crontab entry (run as user with sudo/docker rights):
```cron
# Run Vaultwarden backup daily at 2:30 AM
30 2 * * * /path/to/your/venv/bin/vaultwarden-backup backup --config /path/to/your/config.yaml >> /path/to/vaultwarden_backup.log 2>&1
```

However, the recommended approach for automated backups is using **Docker** with `docker-compose.yaml` (or `docker run`) as shown in the "Run Scheduler" section. This runs the tool's built-in scheduler within the container.

## Docker Usage

You can build and run this tool as a Docker container for automated backups or manual restores. The provided `Dockerfile` sets up the necessary environment.

**Image:** The examples below use the pre-built image from the GitLab registry: `registry.gitlab.notyouraverage.dev/a.anand.91119/vaultwarden-backup:latest`. You can also build your own.

**Building the Image:**

```bash
# Navigate to the directory containing the Dockerfile
docker build -t my-vaultwarden-backup-manager .
```
(Replace `my-vaultwarden-backup-manager` with your preferred local image tag).

### Using `docker run`

See the `Backup (Manual)`, `Restore`, and `Run Scheduler` sections above for `docker run` examples. Remember to:

*   Replace the example image name if you built your own.
*   **Crucially**, correctly map the host paths for:
    *   The Docker socket (`/var/run/docker.sock`).
    *   Your `config.yaml` file.
    *   The Vaultwarden *host* data directory.
    *   The *host* backup storage directory.
    *   For restore: The *parent* directory of the host restore location.
*   Ensure the **target paths** inside the container (e.g., `/config/config.yaml`, `/data`, `/backup`) match the paths specified in your `config.yaml`.
*   **Security Warning:** Mounting the Docker socket (`/var/run/docker.sock`) grants the container significant privileges on your host system. Understand the implications before using it.

### Using `docker compose`

Two Docker Compose files are provided for convenience:

*   `docker-compose.yaml`: For running the continuous backup service (uses the scheduler).
*   `docker-compose.restore.yaml`: For executing a one-off restore task.

**Running the Backup Service (`docker-compose.yaml`):**

1.  Edit `docker-compose.yaml`:
    *   Verify the `image:` tag.
    *   **Crucially**, set the correct **host paths** (left side) in the `volumes:` section for `config.yaml`, the Vaultwarden data directory, and the backup storage directory.
2.  Edit `config.yaml`: Ensure paths like `vaultwarden.data_dir` and `backup.destination.path` match the **target paths** (right side) in the `docker-compose.yaml` volumes. Also configure `backup.schedule.interval_minutes`.
3.  Start the backup service in the background:
    ```bash
    docker compose up -d backup
    ```
4.  View logs:
    ```bash
    docker compose logs -f backup
    ```
5.  Stop the service:
    ```bash
    docker compose down
    ```

**Running a Restore Task (`docker-compose.restore.yaml`):**

1.  Edit `docker-compose.restore.yaml`:
    *   Verify the `image:` tag.
    *   Ensure the **host paths** in the `volumes` section are correct, especially the backup storage and the *parent* directory for the restore target.
    *   Make sure the `config.yaml` mounted is the *same one* used for backups.
2.  Run the restore task using `docker compose -f docker-compose.restore.yaml run restore ...`. The script command (`restore`) and its arguments are appended after the service name (`restore`).
    ```bash
    # Make sure Vaultwarden container is stopped if restoring to its live data dir!
    # docker stop <your-vaultwarden-container-name>

    # Example: Restore latest backup, prompting for confirmation
    docker compose -f docker-compose.restore.yaml run --rm restore \\
      restore --config /config/config.yaml --backup-id latest --target-dir /target/data_dir_name

    # Example: Restore specific backup, skipping confirmation
    docker compose -f docker-compose.restore.yaml run --rm restore \\
      restore --config /config/config.yaml --backup-id <TIMESTAMP_ID> --target-dir /target/data_dir_name --yes
    ```
*   `-f docker-compose.restore.yaml` specifies the file to use.
*   `run --rm restore` tells compose to run the `restore` service defined in that file, execute the command provided after it, and remove the container (`--rm`) when finished.
*   Adjust the command arguments (`--backup-id`, `--target-dir`, `--yes`) as needed.
*   Remember to replace `/target/data_dir_name` with the correct path *inside the container*, corresponding to the desired subdirectory within the host path mounted to `/target`.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details (or refer to `license` field in `pyproject.toml`).

## Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues on the [primary repository](https://gitlab.notyouraverage.dev/a.anand.91119/vaultwarden-backup).
