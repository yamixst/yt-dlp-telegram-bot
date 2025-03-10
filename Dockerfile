FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir yt-dlp

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create downloads directory
RUN mkdir -p /app/downloads

# Copy application files
COPY app/ ./app/
COPY config.toml .

# Create non-root user
RUN useradd -m -u 1000 botuser && \
    chown -R botuser:botuser /app
USER botuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import os; exit(0 if os.path.exists('/app/app/bot.py') else 1)" || exit 1

# Run the bot
CMD ["python", "/app/app/bot.py"]
