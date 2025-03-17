#!/bin/bash

# run-in-venv.sh - Run yt-dlp-telegram-bot in Python virtual environment

set -e

# Configuration
VENV_DIR=".venv"
PYTHON_VERSION="python3"
REQUIREMENTS_FILE="requirements.txt"
BOT_SCRIPT="app/bot.py"

echo "Setting up and running yt-dlp-telegram-bot in virtual environment..."

# Check if config.toml exists
if [ ! -f "config.toml" ]; then
    echo "❌ Error: config.toml not found!"
    echo "Please copy config.example.toml to config.toml and configure it."
    exit 1
fi

# Check if bot script exists
if [ ! -f "$BOT_SCRIPT" ]; then
    echo "❌ Error: $BOT_SCRIPT not found!"
    exit 1
fi

# Create downloads directory if it doesn't exist
mkdir -p downloads

# Create virtual environment if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    $PYTHON_VERSION -m venv "$VENV_DIR"
    echo "✅ Virtual environment created in $VENV_DIR"
fi

# Activate virtual environment
echo "Activating virtual environment..."
source "$VENV_DIR/bin/activate"

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip

# Install requirements if requirements.txt exists
if [ -f "$REQUIREMENTS_FILE" ]; then
    echo "Installing requirements from $REQUIREMENTS_FILE..."
    pip install -r "$REQUIREMENTS_FILE"
    echo "✅ Requirements installed"
else
    echo "⚠️  Warning: $REQUIREMENTS_FILE not found, skipping dependency installation"
fi

# Run the bot
echo ""
echo "🚀 Starting yt-dlp-telegram-bot..."
echo "Press Ctrl+C to stop the bot"
echo ""

cd app
python bot.py --config "../config.toml" --downloads "../downloads"
