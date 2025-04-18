FROM python:3.11-slim-bookworm

# Set working directory
WORKDIR /app

# Install dependencies: cron, gpg (for encryption), docker-cli (to talk to host daemon), gzip, tar
RUN apt-get update && apt-get install -y --no-install-recommends \
    cron \
    gnupg \
    gzip \
    tar \
    docker-ce-cli \
    && rm -rf /var/lib/apt/lists/*

# Copy application files
COPY requirements.txt requirements.txt
COPY bw_manager.py bw_manager.py
COPY entrypoint.sh entrypoint.sh

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Make entrypoint executable
RUN chmod +x entrypoint.sh

# Define volume mount points (optional, but good practice)
# /config: For mounting config.yaml
# /data: For mounting the host's Vaultwarden data directory (read-only for backup)
# /backup: For mounting the host's backup storage directory
VOLUME ["/config", "/data", "/backup"]

# Set the entrypoint
ENTRYPOINT ["/app/entrypoint.sh"]

# Default command (cron in foreground)
CMD ["cron", "-f"] 
