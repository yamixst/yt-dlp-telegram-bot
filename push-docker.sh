#!/bin/bash

# push-docker.sh - Push Docker image to registry

set -e

# Configuration
IMAGE_NAME="yt-dlp-telegram-bot"
TAG="${1:-latest}"
REGISTRY="${2:-docker.io}"
REPOSITORY="${3:-yamixst}"

# Full image name with registry
FULL_IMAGE_NAME="${REGISTRY}/${REPOSITORY}/${IMAGE_NAME}:${TAG}"

echo "Pushing Docker image to registry..."
echo "Local image: ${IMAGE_NAME}:${TAG}"
echo "Registry image: ${FULL_IMAGE_NAME}"

# Check if local image exists
if ! docker images "${IMAGE_NAME}:${TAG}" --format "table {{.Repository}}:{{.Tag}}" | grep -q "${IMAGE_NAME}:${TAG}"; then
    echo "❌ Error: Local image ${IMAGE_NAME}:${TAG} not found!"
    echo "Please build the image first using: ./build-docker.sh"
    exit 1
fi

# Tag the image for the registry
echo "Tagging image for registry..."
docker tag "${IMAGE_NAME}:${TAG}" "${FULL_IMAGE_NAME}"

# Push to registry
echo "Pushing to registry..."
docker push "${FULL_IMAGE_NAME}"

echo "✅ Successfully pushed image: ${FULL_IMAGE_NAME}"

# Clean up local registry tag (optional)
echo ""
read -p "Remove local registry tag? [y/N]: " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    docker rmi "${FULL_IMAGE_NAME}"
    echo "Local registry tag removed."
fi

echo ""
echo "Image is now available at: ${FULL_IMAGE_NAME}"
echo "To pull: docker pull ${FULL_IMAGE_NAME}"
