FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system botuser && \
    useradd --system --gid botuser botuser && \
    mkdir -p /downloads && \
    chown -R botuser:botuser /downloads

VOLUME ["/downloads", "/app/config.toml"]

ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_NO_CACHE_DIR=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY --chown=botuser:botuser app/*.py /app/

USER botuser

CMD ["python", "bot.py"]
