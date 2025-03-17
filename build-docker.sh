#!/bin/bash

# build-docker.sh - Build Docker image for yt-dlp-telegram-bot

set -e

# Configuration
IMAGE_NAME="yt-dlp-telegram-bot"
TAG="${1:-latest}"
DOCKERFILE="${2:-Dockerfile}"

echo "Building Docker image: ${IMAGE_NAME}:${TAG}"

# Build the Docker image
docker build \
    --tag "${IMAGE_NAME}:${TAG}" \
    --file "${DOCKERFILE}" \
    .

echo "✅ Successfully built Docker image: ${IMAGE_NAME}:${TAG}"

# Show image info
echo ""
echo "Image details:"
docker images "${IMAGE_NAME}:${TAG}"
