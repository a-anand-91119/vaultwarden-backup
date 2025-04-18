# Vaultwarden Docker Backup & Restore Manager

This Python script provides automated backup and restore capabilities for a Vaultwarden Docker container installation.

## Features

*   **Automated Backups:** Creates timestamped, compressed archives (`.tar.gz`) of the entire Vaultwarden data directory.
*   **Automated Restores:** Restores a specified backup to the target data directory.
*   **Encryption:** Optionally encrypts backups using GPG.
*   **Retention Policy:** Automatically deletes older backups based on configurable daily, weekly, and monthly retention settings.
*   **Configurable:** Uses a YAML file for configuration.
*   **Logging:** Logs operations to both console and a file.
*   **Container Management:** Stops and starts the specified Vaultwarden container during backup/restore for data consistency.

## Prerequisites

*   Python 3.6+
*   `PyYAML` Python package (`pip install PyYAML` or `pip install -r requirements.txt`)
*   A running Vaultwarden instance in a Docker container.
*   Access to the Docker host machine.
*   The `docker` command-line tool installed and accessible.
*   Necessary command-line tools installed:
    *   `tar`, `gzip` (usually standard)
    *   `gpg` (if using encryption)
*   **Sudo privileges are likely required** for:
    *   Running `docker stop`/`start` commands.
    *   The `restore` command if setting file ownership (`owner_uid`/`owner_gid` in config) or deleting existing data owned by another user.

## Setup

1.  **Copy Files:** Place `bw_manager.py` (you might want to rename it to `vaultwarden_manager.py`), `config.yaml.example`, and `requirements.txt` somewhere accessible on your Docker host.
2.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
3.  **Create Configuration:**
    *   Copy `config.yaml.example` to `config.yaml` (or another name).
    *   Edit `config.yaml` and fill in the required paths and settings:
        *   `vaultwarden.container_name`: The exact name or ID of your running Vaultwarden container.
        *   `vaultwarden.data_dir`: The full path on the **host** machine where your Vaultwarden data volume is mounted.
        *   `backup.destination.path`: The directory where backup archives should be stored.
        *   Configure `backup.encryption` and `backup.retention` as needed.
        *   `backup.restore.temp_dir`: A temporary directory for restore operations.
        *   `backup.restore.owner_uid`, `backup.restore.owner_gid`: **Important for restore:** Set these to the numeric UID and GID that the Vaultwarden container runs as (often set via `PUID` and `PGID` environment variables when starting the container). This ensures correct permissions after restoring. Leave blank to skip setting permissions (restore might fail).
4.  **Make Executable (Optional):** `chmod +x bw_manager.py`

## Usage

Use the script via the command line. Remember you might need `sudo`.

**Configuration File:** Always specify the configuration file using `--config` (e.g., `--config config.yaml`).

**Log File:** Logs are written to `vaultwarden_manager.log` by default. Change with `--log-file`.

**Verbose Logging:** Add `-v` or `--verbose` for DEBUG level logging.

### Backup

```bash
# Basic backup (likely needs sudo to run docker stop/start)
sudo ./bw_manager.py backup --config /path/to/your/config.yaml

# Backup with verbose logging
sudo ./bw_manager.py backup --config /path/to/your/config.yaml -v
```

This will:
1.  Stop the Vaultwarden container (`docker stop`).
2.  Create a timestamped `.tar.gz` archive of the configured `data_dir`.
3.  Encrypt the archive with GPG if configured.
4.  Start the Vaultwarden container (`docker start`).
5.  Apply the retention policy, deleting older backups in the destination path.

### Restore

**WARNING:** Restore is a destructive operation. It will stop the Vaultwarden container, delete the existing data directory on the host, and replace it with the contents of the selected backup.

**SUDO:** You will likely need to run the restore command with `sudo`.

```bash
# Restore the latest backup (requires confirmation)
sudo ./bw_manager.py restore --config /path/to/your/config.yaml --backup-id latest

# Restore a specific backup by timestamp ID (requires confirmation)
sudo ./bw_manager.py restore --config /path/to/your/config.yaml --backup-id 20230115T103000

# Restore the latest backup, skipping confirmation (DANGEROUS!)
sudo ./bw_manager.py restore --config /path/to/your/config.yaml --backup-id latest --yes

# Restore TO a different target data directory path (e.g., migrating)
# Ensure the container is NOT running and pointed to this new dir before starting it after restore
sudo ./bw_manager.py restore --config /path/to/your/config.yaml --backup-id latest --target-dir /path/to/new/data_dir
```

This will:
1.  Find the specified backup archive in the configured destination path.
2.  Copy it to the configured temporary restore directory.
3.  Decrypt it if necessary.
4.  Stop the Vaultwarden container (`docker stop`).
5.  **Prompt for confirmation** before deleting data (unless `--yes` is used).
6.  Delete the existing data directory at the target path.
7.  Extract the backup archive content into the parent of the target path, recreating the data directory.
8.  Attempt to set ownership (`chown`) and permissions (`chmod`) on the restored data directory using the configured UID/GID (requires `sudo`).
9.  Start the Vaultwarden container (`docker start`).
10. Clean up the temporary directory.

## Automation (Scheduling Backups)

You can schedule regular backups using `cron`.

1.  Edit the crontab, likely for the `root` user or a user with passwordless `sudo` rights for `docker` commands:
    ```bash
    sudo crontab -e
    ```
2.  Add a line similar to this to run the backup daily at 2:30 AM:
    ```cron
    # Example: Run Vaultwarden backup daily at 2:30 AM
    30 2 * * * /usr/bin/python3 /path/to/bw_manager.py backup --config /path/to/your/config.yaml >> /path/to/vaultwarden_manager.log 2>&1
    ```
    *   Adjust the paths to `python3`, `bw_manager.py` (or your renamed script), `config.yaml`, and the log file.
    *   Ensure the command runs with sufficient privileges (e.g., via `sudo crontab` or ensuring the user can run `docker` without a password).

## Future Enhancements

*   Support for SSH and S3-compatible backup destinations.
*   More sophisticated notification options (email, webhooks).
*   Optional database-specific backup commands (e.g., SQLite `.backup`) before archiving?
*   More robust error handling for different storage backends.

## Docker Usage

You can build and run this tool as a Docker container for automated backups or manual restores.

**Building the Image:**

```bash
# Navigate to the directory containing the Dockerfile
docker build -t vaultwarden-backup-manager . 
```

(Replace `vaultwarden-backup-manager` with your preferred image tag).

### Using `docker run`

**Running the Backup Container (`docker run`):**

This container runs continuously in the background, executing backups based on the cron schedule defined by the `CRON_SCHEDULE` environment variable (defaults to `30 2 * * *`).

*   **Crucially**, you need to mount:
    *   The host's Docker socket (`/var/run/docker.sock`) so the container can control the Vaultwarden container.
    *   Your `config.yaml` file.
    *   The host directory containing your Vaultwarden data (read-only).
    *   The host directory where backups should be stored.

```bash
docker run -d \
  --name vaultwarden-backup \
  --restart=unless-stopped \
  -e CRON_SCHEDULE="0 3 * * *" `# Optional: Run daily at 3:00 AM` \
  -e VERBOSE_LOGGING="false"   `# Optional: Set to true for verbose script logs` \
  -e TZ="America/New_York"     `# Optional: Set your timezone` \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v $(pwd)/config.yaml:/config/config.yaml:ro `# Mount config read-only` \
  -v /path/to/vaultwarden/host/data-directory:/data:ro `# Mount data read-only for backup` \
  -v /path/to/your/backup/storage:/backup `# Mount backup storage` \
  vaultwarden-backup-manager 
```

*   Adjust host paths for `config.yaml`, `data-directory`, and `backup/storage`.
*   Ensure paths inside the container (`/config/config.yaml`, `/data`, `/backup`) align with your `config.yaml` settings (`vaultwarden.data_dir`, `backup.destination.path`).
*   **Security Warning:** Mounting the Docker socket grants high privileges.
*   View logs with `docker logs vaultwarden-backup`.

**Running a Restore Task (`docker run`):**

Restore is a manual, one-off task using a temporary container.

*   Mount:
    *   Docker socket.
    *   `config.yaml` (read-only).
    *   Backup storage (read-only).
    *   **Parent directory** of the host restore location (read-write).

```bash
# Make sure Vaultwarden container is stopped if restoring to its current data dir!
# docker stop <your-vaultwarden-container-name>

docker run --rm -it \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v $(pwd)/config.yaml:/config/config.yaml:ro \
  -v /path/to/your/backup/storage:/backup:ro `# Mount backup storage read-only` \
  -v /path/to/vaultwarden/host/parent-directory:/target `# Mount parent of data dir RW` \
  vaultwarden-backup-manager restore \
    --config /config/config.yaml \
    --backup-id latest `# Or a specific ID` \
    --target-dir /target/data_dir_name `# Path INSIDE container where data should be restored` \
    # --yes # Add this to skip confirmation (DANGEROUS!)
```

*   Adjust host paths and `--target-dir` (which is the path *inside* the container).
*   The script attempts to stop/start the container from `config.yaml`.
*   The script needs write access to the target mount (`/target`).

### Using `docker compose`

Two Docker Compose files are provided:
*   `docker-compose.yaml`: For running the continuous backup service.
*   `docker-compose.restore.yaml`: For executing a one-off restore task.

**Running the Backup Service (`docker-compose.yaml`):**

1.  Edit `docker-compose.yaml`: Set the correct `image` tag and adjust the host paths in the `volumes` section for the `backup` service.
2.  Start the backup service in the background:
    ```bash
    docker compose up -d backup
    ```
3.  View logs:
    ```bash
    docker compose logs -f backup
    ```
4.  Stop the service:
    ```bash
    # This stops and removes the container defined in docker-compose.yaml
    docker compose down
    ```

**Running a Restore Task (`docker-compose.restore.yaml`):**

1.  Edit `docker-compose.restore.yaml`: Ensure the `image` tag and host paths in the `volumes` section are correct. Make sure the config file mounted is the *same one* used for backups.
2.  Run the restore task using `docker compose -f docker-compose.restore.yaml run`. You append the script command (`restore`) and its arguments after the service name (`restore`).

    ```bash
    # Make sure Vaultwarden container is stopped if restoring to its current data dir!
    # docker stop <your-vaultwarden-container-name>

    # Example: Restore latest backup
    docker compose -f docker-compose.restore.yaml run --rm restore \
      restore --config /config/config.yaml --backup-id latest --target-dir /target/data_dir_name

    # Example: Restore specific backup, skipping confirmation
    docker compose -f docker-compose.restore.yaml run --rm restore \
      restore --config /config/config.yaml --backup-id 20230115T103000 --target-dir /target/data_dir_name --yes
    ```

*   `-f docker-compose.restore.yaml` specifies the file to use.
*   `run --rm restore` tells compose to run the `restore` service defined in that file and remove the container (`--rm`) when finished.
*   The subsequent `restore --config ...` are the arguments passed to the `bw_manager.py` script inside the container.
*   Adjust the command arguments (`--backup-id`, `--target-dir`, `--yes`) as needed.
*   Remember to replace `/target/data_dir_name` with the correct path inside the container, corresponding to the host path mounted to `/target`.