# YouTube Downloader Telegram Bot

A Telegram bot that allows you to download videos and audio from various platforms using [yt-dlp](https://github.com/yt-dlp/yt-dlp). Simply send a URL to the bot and choose your preferred format.

## Features

- 🎥 Download videos from multiple platforms (YouTube, Vimeo, TikTok, Instagram, Twitter, Reddit, Twitch, Dailymotion)
- 🎵 Extract audio in MP3 format
- 📱 Easy-to-use Telegram interface with inline buttons
- ⚙️ Configurable quality settings and file size limits
- 🔒 User access control with allowed chat IDs
- 📊 Real-time download progress updates
- 🐳 Docker support for easy deployment
- 🧹 Automatic cleanup of downloaded files
- ⏱️ Duration and file size limits to prevent abuse

## Supported Platforms

- YouTube
- Vimeo
- TikTok
- Instagram
- Twitter/X
- Reddit
- Twitch
- Dailymotion

## Quick Start

### Using Docker (Recommended)

1. Clone the repository:
```bash
git clone https://github.com/yourusername/yt-dlp-telegram-bot.git
cd yt-dlp-telegram-bot
```

2. Copy the example configuration:
```bash
cp config.example.toml config.toml
```

3. Edit `config.toml` and add your bot token:
```toml
[telegram]
bot_token = "YOUR_BOT_TOKEN_HERE"
```

4. Build and run with Docker:
```bash
./build-docker.sh
./run-in-docker.sh
```

### Manual Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/yt-dlp-telegram-bot.git
cd yt-dlp-telegram-bot
```

2. Create a virtual environment:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Copy and configure the settings:
```bash
cp config.example.toml config.toml
# Edit config.toml with your settings
```

5. Run the bot:
```bash
./run-in-venv.sh
```

## Configuration

### Getting a Bot Token

1. Message [@BotFather](https://t.me/BotFather) on Telegram
2. Send `/newbot` and follow the instructions
3. Copy the bot token and add it to your `config.toml`

### Finding Your Chat ID

1. Start your bot and send it a message
2. Check the bot logs to find your chat ID
3. Add your chat ID to the `allowed_chat_ids` list in `config.toml`

### Configuration Options

The bot is configured through `config.toml`. Key settings include:

- **Bot Token**: Your Telegram bot token from BotFather
- **File Size Limit**: Maximum file size for downloads (Telegram limit is 50MB)
- **Quality Settings**: Video quality preferences for yt-dlp
- **Duration Limits**: Maximum video duration allowed
- **Supported Sites**: Enable/disable specific platforms
- **Access Control**: Restrict bot usage to specific users

Example configuration:

```toml
[telegram]
bot_token = "YOUR_BOT_TOKEN"
max_file_size_mb = 50
allowed_chat_ids = [123456789]

[download]
output_dir = "/app/downloads"
max_duration_minutes = 60
quality = "best[height<=720]"
audio_format = "mp3"
video_format = "mp4"
```

## Usage

1. Start a chat with your bot
2. Send a video URL from any supported platform
3. Choose your preferred format:
   - 🎥 **Video**: Download as MP4
   - 🎵 **Audio**: Extract audio as MP3
4. Wait for the download to complete
5. The bot will send you the file directly in Telegram

## Docker Deployment

### Using Docker Compose

```bash
docker-compose up -d
```

### Building Custom Image

```bash
./build-docker.sh
```

### Environment Variables

You can also configure the bot using environment variables:

- `TELEGRAM_BOT_TOKEN`: Your bot token
- `ALLOWED_CHAT_IDS`: Comma-separated list of allowed chat IDs

## Development

### Project Structure

```
yt-dlp-telegram-bot/
├── app/
│   └── bot.py              # Main bot application
├── downloads/              # Downloaded files directory
├── config.example.toml     # Example configuration
├── requirements.txt        # Python dependencies
├── Dockerfile             # Docker configuration
├── docker-compose.yml     # Docker Compose setup
└── README.md              # This file
```

### Running in Development

1. Install dependencies in a virtual environment
2. Copy `config.example.toml` to `config.toml`
3. Configure your bot token and settings
4. Run with `python app/bot.py`

### Adding New Platforms

The bot uses yt-dlp, which supports hundreds of sites. To add support for a new platform:

1. Add the platform to the `supported_sites` section in `config.toml`
2. Update the `is_supported_url()` method in `bot.py`
3. Test with URLs from the new platform

## Limitations

- Telegram has a 50MB file size limit for bots
- Some platforms may have rate limits or require authentication
- Video duration and quality limits are configurable
- The bot respects copyright and terms of service of source platforms

## Troubleshooting

### Common Issues

1. **Bot not responding**: Check your bot token and ensure the bot is started
2. **Downloads failing**: Verify the URL is from a supported platform
3. **File too large**: Reduce quality settings or use audio-only mode
4. **Permission denied**: Check that your chat ID is in the allowed list

### Logs

Check the bot logs for detailed error messages:

```bash
# Docker
docker logs yt-dlp-telegram-bot

# Manual installation
# Logs are printed to console
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Disclaimer

This tool is for educational and personal use only. Users are responsible for complying with the terms of service of the platforms they download content from. Respect copyright laws and content creators' rights.

## Acknowledgments

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) - The powerful video downloader
- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) - Telegram Bot API wrapper
- All contributors and users of this project
