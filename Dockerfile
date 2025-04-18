FROM python:3.11-slim-bookworm

# Set working directory
WORKDIR /app

# Install dependencies: gpg (for encryption), docker-cli (to talk to host daemon), gzip, tar
RUN apt-get update && \
    # Install prerequisites for Docker repo
    apt-get install -y --no-install-recommends ca-certificates curl gnupg && \
    # Add Docker's official GPG key
    install -m 0755 -d /etc/apt/keyrings && \
    curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg && \
    chmod a+r /etc/apt/keyrings/docker.gpg && \
    # Set up the Docker repository
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian \
      $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
      tee /etc/apt/sources.list.d/docker.list > /dev/null && \
    # Update apt package index again after adding repo
    apt-get update && \
    # Install the required packages (removed cron)
    apt-get install -y --no-install-recommends \
      gnupg \
      gzip \
      tar \
      docker-ce-cli \
    && \
    # Clean up
    rm -rf /var/lib/apt/lists/*

# Copy application files (removed entrypoint.sh)
COPY requirements.txt requirements.txt
COPY bw_manager.py bw_manager.py

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# No need to chmod entrypoint anymore
# RUN chmod +x entrypoint.sh

# Define volume mount points (optional, but good practice)
# /config: For mounting config.yaml
# /data: For mounting the host's Vaultwarden data directory (read-only for backup)
# /backup: For mounting the host's backup storage directory
VOLUME ["/config", "/data", "/backup"]

# Remove ENTRYPOINT
# ENTRYPOINT ["/app/entrypoint.sh"]

# Default command: Run the Python script in scheduler mode
CMD ["python3", "/app/bw_manager.py", "run-scheduler", "--config", "/config/config.yaml"] 
