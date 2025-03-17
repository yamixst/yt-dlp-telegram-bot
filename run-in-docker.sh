#!/bin/bash

# run-in-docker.sh - Run yt-dlp-telegram-bot in Docker container

set -e

# Configuration
IMAGE_NAME="yt-dlp-telegram-bot"
TAG="${1:-latest}"
CONTAINER_NAME="yt-dlp-telegram-bot"

# Check if config.toml exists
if [ ! -f "config.toml" ]; then
    echo "❌ Error: config.toml not found!"
    echo "Please copy config.example.toml to config.toml and configure it."
    exit 1
fi

# Create downloads directory if it doesn't exist
mkdir -p downloads

echo "Running Docker container: ${CONTAINER_NAME}"

# Stop and remove existing container if it exists
if docker ps -a --format 'table {{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "Stopping existing container..."
    docker stop "${CONTAINER_NAME}" || true
    docker rm "${CONTAINER_NAME}" || true
fi

# Run the container
docker run -d \
    --name "${CONTAINER_NAME}" \
    --restart unless-stopped \
    -v "$(pwd)/downloads:/downloads" \
    -v "$(pwd)/config.toml:/app/config.toml:ro" \
    "${IMAGE_NAME}:${TAG}"

echo "✅ Container started successfully!"
echo ""
echo "To view logs: docker logs -f ${CONTAINER_NAME}"
echo "To stop: docker stop ${CONTAINER_NAME}"
echo "To restart: docker restart ${CONTAINER_NAME}"
