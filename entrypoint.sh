#!/bin/sh

# Exit immediately if a command exits with a non-zero status.
set -e

# --- Configuration Variables ---
# These can be overridden by Docker environment variables (-e)

# Cron schedule for backups
CRON_SCHEDULE=${CRON_SCHEDULE:-"30 2 * * *"} # Default: 2:30 AM daily

# Path to the config file inside the container
CONFIG_PATH=${CONFIG_PATH:-"/config/config.yaml"}

# Path for the log file inside the container (should likely be in a mounted volume)
LOG_PATH=${LOG_PATH:-"/backup/vaultwarden_manager.log"}

# Python command
PYTHON_CMD=${PYTHON_CMD:-"python3"}

# Path to the script inside the container
SCRIPT_PATH=${SCRIPT_PATH:-"/app/bw_manager.py"}

# Verbose flag (-v)
VERBOSE_FLAG=""
if [ "${VERBOSE_LOGGING}" = "true" ] || [ "${VERBOSE_LOGGING}" = "1" ]; then
  VERBOSE_FLAG="-v"
fi

# --- Sanity Checks ---
if [ ! -f "${CONFIG_PATH}" ]; then
    echo "[Error] Configuration file not found at ${CONFIG_PATH}!" >&2
    echo "Please mount your config.yaml to ${CONFIG_PATH}" >&2
    exit 1
fi

# Check if docker socket is mounted (basic check)
if [ ! -S /var/run/docker.sock ]; then
    echo "[Warning] Docker socket not found at /var/run/docker.sock." >&2
    echo "The script needs access to the host Docker socket to stop/start the Vaultwarden container." >&2
    # Don't exit, maybe user runs manually without stop/start needed?
fi

# --- Create Crontab ---
# Using root user's crontab. Cron needs to run as root to have rights to modify this.
# Redirect cron job output to the container's stdout/stderr, which can be viewed with `docker logs`
# NOTE: This assumes the script handles its own detailed file logging via --log-file

# Build the command to run
BACKUP_CMD="${PYTHON_CMD} ${SCRIPT_PATH} backup --config ${CONFIG_PATH} --log-file ${LOG_PATH} ${VERBOSE_FLAG}"

echo "Setting up cron schedule: '${CRON_SCHEDULE}' for user root" 
echo "Command: ${BACKUP_CMD}"

# Create the crontab file in /etc/cron.d/
# Files in /etc/cron.d need the user field (root in this case)
CRON_FILE="/etc/cron.d/backup-job"

# Add SHELL variable for safety, ensure PATH includes docker binary location
# Cron usually has a minimal environment, explicitly set PATH
DOCKER_PATH=$(which docker || echo "/usr/bin/docker") # Find docker path
CRON_ENV="SHELL=/bin/sh\nPATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

# Ensure the file ends with a newline for cron
echo -e "${CRON_ENV}\n${CRON_SCHEDULE} root ${BACKUP_CMD} >> /proc/1/fd/1 2>> /proc/1/fd/2\n" > ${CRON_FILE}

# Set correct permissions for crontab file in /etc/cron.d/
# Typically requires root ownership and restricted write permissions
chmod 0644 ${CRON_FILE}

# --- Start Cron Daemon ---
echo "Starting cron daemon..."

# Use exec to replace the shell process with cron, making cron PID 1
exec "$@" 