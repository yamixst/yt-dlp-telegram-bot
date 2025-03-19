#!/usr/bin/env python3
"""
Telegram Bot for downloading videos using yt-dlp
"""

import argparse
import asyncio
import logging
import os
import time
from pathlib import Path
from urllib.parse import urlparse

import toml
import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters


class VideoDownloader:
    def __init__(self, config):
        self.config = config
        self.download_dir = Path(config['download']['output_dir'])
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.active_downloads = {}
        self.progress_data = {}

        logging.basicConfig(
            format=config['logging']['format'],
            level=getattr(logging, config['logging']['level'])
        )
        self.logger = logging.getLogger(__name__)

        # Log proxy configuration
        proxy_settings = self.config.get('proxy', {})
        if proxy_settings.get('http_proxy') or proxy_settings.get('https_proxy'):
            proxy_url = proxy_settings.get('http_proxy') or proxy_settings.get('https_proxy')
            self.logger.info(f"Proxy configured: {proxy_url}")
        else:
            self.logger.info("No proxy configured")

    def _get_proxy_config(self):
        """Get proxy configuration for yt-dlp"""
        proxy_config = {}
        proxy_settings = self.config.get('proxy', {})

        if proxy_settings.get('http_proxy'):
            proxy_config['proxy'] = proxy_settings['http_proxy']
        elif proxy_settings.get('https_proxy'):
            proxy_config['proxy'] = proxy_settings['https_proxy']

        return proxy_config

    def is_supported_url(self, url):
        """Check if URL is from supported site"""
        try:
            domain = urlparse(url).netloc.lower()
            sites = {
                'youtube': ['youtube.com', 'youtu.be'],
                'vimeo': ['vimeo.com'],
                'dailymotion': ['dailymotion.com'],
                'twitch': ['twitch.tv'],
                'tiktok': ['tiktok.com'],
                'instagram': ['instagram.com'],
                'twitter': ['twitter.com', 'x.com'],
                'reddit': ['reddit.com']
            }

            for site, domains in sites.items():
                if self.config['supported_sites'].get(site, False):
                    if any(d in domain for d in domains):
                        return True
            return False
        except:
            return False

    def _progress_hook(self, d, chat_id):
        """Progress hook for yt-dlp"""
        if d['status'] == 'downloading':
            self.progress_data[chat_id] = {
                'downloaded_bytes': d.get('downloaded_bytes', 0),
                'total_bytes': d.get('total_bytes') or d.get('total_bytes_estimate', 0),
                'speed': d.get('speed', 0),
                'eta': d.get('eta', 0)
            }

    async def get_video_info(self, url):
        """Get video information using yt-dlp"""
        def _extract_info():
            try:
                ydl_opts = {
                    'quiet': True,
                    'no_warnings': True,
                    'extract_flat': False,
                }

                # Add proxy configuration
                ydl_opts.update(self._get_proxy_config())

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return ydl.extract_info(url, download=False)
            except Exception as e:
                self.logger.error(f"Error getting video info: {e}")
                return None

        # Run in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, _extract_info)

        if not info:
            return None

        duration = info.get('duration', 0)
        filesize = info.get('filesize') or info.get('filesize_approx')

        estimated_size_mb = None
        if filesize:
            estimated_size_mb = filesize / (1024 * 1024)
        elif duration:
            estimated_size_mb = duration / 60  # ~1MB per minute

        return {
            'title': info.get('title', 'Unknown'),
            'duration': duration,
            'uploader': info.get('uploader', 'Unknown'),
            'estimated_size_mb': estimated_size_mb,
        }

    async def download_video(self, url, chat_id, format_type='video', status_message=None):
        """Download video using yt-dlp"""
        def _download():
            try:
                timestamp = int(time.time())
                output_template = str(self.download_dir / f"{chat_id}_{timestamp}_%(title)s.%(ext)s")

                ydl_opts = {
                    'outtmpl': output_template,
                    'noplaylist': True,
                    'nocheckcertificate': True,
                    'quiet': True,
                    'no_warnings': True,
                    'progress_hooks': [lambda d: self._progress_hook(d, chat_id)],
                }

                # Add proxy configuration
                ydl_opts.update(self._get_proxy_config())

                if format_type == 'audio':
                    ydl_opts.update({
                        'format': 'bestaudio',
                        'postprocessors': [{
                            'key': 'FFmpegExtractAudio',
                            'preferredcodec': self.config['download']['audio_format'],
                            'preferredquality': '0',
                        }]
                    })
                else:
                    ydl_opts.update({
                        'format': f"{self.config['download']['quality']}/best/worst",
                        'merge_output_format': self.config['download']['video_format'],
                    })

                self.logger.info(f"Starting download: {url}")
                self.active_downloads[chat_id] = {'url': url, 'start_time': time.time(), 'format': format_type}

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])

                # Find downloaded file
                files = list(self.download_dir.glob(f"{chat_id}_{timestamp}_*"))
                return str(files[0]) if files else None

            except yt_dlp.DownloadError as e:
                self.logger.error(f"Download error: {e}")
                if "Requested format is not available" in str(e) and format_type == 'video':
                    # Retry with simple format
                    try:
                        ydl_opts['format'] = 'best'
                        # Ensure proxy config is still applied for retry
                        ydl_opts.update(self._get_proxy_config())
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                            ydl.download([url])
                        files = list(self.download_dir.glob(f"{chat_id}_{timestamp}_*"))
                        return str(files[0]) if files else None
                    except:
                        return None
                return None
            except Exception as e:
                self.logger.error(f"Download error: {e}")
                return None
            finally:
                self.active_downloads.pop(chat_id, None)
                self.progress_data.pop(chat_id, None)

        try:
            if status_message:
                asyncio.create_task(self._monitor_progress(status_message, chat_id))

            # Run download in thread pool
            loop = asyncio.get_event_loop()
            file_path = await asyncio.wait_for(
                loop.run_in_executor(None, _download),
                timeout=self.config['limits']['download_timeout_seconds']
            )

            return file_path

        except asyncio.TimeoutError:
            self.logger.error("Download timeout")
            self.active_downloads.pop(chat_id, None)
            self.progress_data.pop(chat_id, None)
            return None

    async def _monitor_progress(self, status_message, chat_id):
        """Monitor download progress"""
        if not self.config['download'].get('show_download_progress', True):
            return

        try:
            count = 0
            interval = self.config['download'].get('progress_update_interval_seconds', 3)
            last_bytes = 0

            while chat_id in self.active_downloads:
                await asyncio.sleep(interval)

                progress = self.progress_data.get(chat_id, {})
                downloaded = progress.get('downloaded_bytes', 0)

                # Update only if significant change
                if downloaded - last_bytes > 512 * 1024:  # 512KB threshold
                    last_bytes = downloaded
                    count += 1
                    dots = "." * (count % 4)

                    size_mb = downloaded / (1024 * 1024)
                    speed = progress.get('speed', 0)

                    status_text = f"Downloading{dots} {size_mb:.1f} MB"
                    if speed:
                        speed_mb = speed / (1024 * 1024)
                        status_text += f" ({speed_mb:.1f} MB/s)"

                    try:
                        await status_message.edit_text(status_text)
                    except:
                        pass

        except Exception as e:
            self.logger.error(f"Progress monitoring error: {e}")

    def cleanup_old_files(self):
        """Clean up old files"""
        try:
            cutoff = time.time() - (self.config['limits']['cleanup_after_hours'] * 3600)
            for file_path in self.download_dir.glob("*"):
                if file_path.is_file() and file_path.stat().st_mtime < cutoff:
                    file_path.unlink()
                    self.logger.info(f"Cleaned up: {file_path}")
        except Exception as e:
            self.logger.error(f"Cleanup error: {e}")


class TelegramBot:
    def __init__(self, config):
        self.config = config
        self.downloader = VideoDownloader(config)
        self.logger = logging.getLogger(__name__)

        self.app = Application.builder().token(config['telegram']['bot_token']).build()
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CommandHandler("status", self.status_command))
        self.app.add_handler(CommandHandler("cleanup", self.cleanup_command))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_url))
        self.app.add_handler(CallbackQueryHandler(self.handle_callback))

    def is_chat_allowed(self, chat_id):
        """Check if chat is allowed"""
        allowed = self.config['telegram']['allowed_chat_ids']
        return not allowed or chat_id in allowed

    async def start_command(self, update, context):
        if not self.is_chat_allowed(update.effective_chat.id):
            await update.message.reply_text("Not authorized.")
            return

        sites = [site.title() for site, enabled in self.config['supported_sites'].items() if enabled]
        text = f"Video Downloader Bot\n\nSend me a video URL.\n\nSupported sites:\n" + "\n".join(f"- {s}" for s in sites) + "\n\nUse /help for more information"
        await update.message.reply_text(text)

    async def help_command(self, update, context):
        if not self.is_chat_allowed(update.effective_chat.id):
            return

        auto_threshold = self.config['download'].get('auto_download_video_under_minutes', 0)
        help_text = "How to use:\n1. Send video URL\n"

        if auto_threshold > 0:
            help_text += f"2. Videos < {auto_threshold} min: auto-download as video\n3. Longer videos: choose format\n"
        else:
            help_text += "2. Choose format (video/audio)\n"

        help_text += f"\nCommands:\n/start - Start\n/help - Help\n/status - Downloads\n/cleanup - Clean files\n\nLimits:\nMax size: {self.config['telegram']['max_file_size_mb']}MB\nMax duration: {self.config['download']['max_duration_minutes']} minutes\nMax concurrent: {self.config['limits']['max_concurrent_downloads']}"

        await update.message.reply_text(help_text)

    async def status_command(self, update, context):
        if not self.is_chat_allowed(update.effective_chat.id):
            return

        active = len(self.downloader.active_downloads)
        if active == 0:
            await update.message.reply_text("No active downloads")
            return

        text = f"Active downloads: {active}\n\n"
        for chat_id, info in self.downloader.active_downloads.items():
            elapsed = int(time.time() - info['start_time'])
            text += f"Chat {chat_id}: {info['format']} ({elapsed}s)\n"

        await update.message.reply_text(text)

    async def cleanup_command(self, update, context):
        if not self.is_chat_allowed(update.effective_chat.id):
            return

        await update.message.reply_text("Starting cleanup...")
        try:
            old_count = len(list(self.downloader.download_dir.glob("*")))
            self.downloader.cleanup_old_files()
            new_count = len(list(self.downloader.download_dir.glob("*")))
            await update.message.reply_text(f"Cleanup completed. Removed {old_count - new_count} files.")
        except Exception as e:
            await update.message.reply_text("Cleanup failed.")

    async def handle_url(self, update, context):
        if not self.is_chat_allowed(update.effective_chat.id):
            await update.message.reply_text("Not authorized.")
            return

        url = update.message.text.strip()
        chat_id = update.effective_chat.id

        if not self.downloader.is_supported_url(url):
            await update.message.reply_text("URL not supported.")
            return

        if len(self.downloader.active_downloads) >= self.config['limits']['max_concurrent_downloads']:
            await update.message.reply_text(f"Max downloads ({self.config['limits']['max_concurrent_downloads']}) reached.")
            return

        if chat_id in self.downloader.active_downloads:
            await update.message.reply_text("Download in progress.")
            return

        status_message = await update.message.reply_text("Getting info...")
        video_info = await self.downloader.get_video_info(url)

        if not video_info:
            await status_message.edit_text("Could not get video info.")
            return

        duration_minutes = video_info.get('duration', 0) / 60
        if duration_minutes > self.config['download']['max_duration_minutes']:
            await status_message.edit_text(f"Video too long ({duration_minutes:.1f} min). Max: {self.config['download']['max_duration_minutes']} min.")
            return

        auto_threshold = self.config['download'].get('auto_download_video_under_minutes', 0)

        if auto_threshold > 0 and duration_minutes < auto_threshold:
            # Auto-download short videos
            size_info = f"Size: {video_info['estimated_size_mb']:.1f} MB\n" if video_info.get('estimated_size_mb') else ""
            await status_message.edit_text(f"{video_info['title']}\nDuration: {duration_minutes:.1f} min\n{size_info}Downloading...")

            await self._download_and_send(url, chat_id, 'video', status_message, context)
        else:
            # Show format options
            size_info = f"Size: {video_info['estimated_size_mb']:.1f} MB\n" if video_info.get('estimated_size_mb') else ""
            info_text = f"{video_info['title']}\nDuration: {duration_minutes:.1f} min\n{size_info}"

            keyboard = [
                [InlineKeyboardButton("Video", callback_data=f"download_video_{url}"),
                 InlineKeyboardButton("Audio", callback_data=f"download_audio_{url}")],
                [InlineKeyboardButton("Cancel", callback_data="cancel")]
            ]

            await status_message.edit_text(info_text, reply_markup=InlineKeyboardMarkup(keyboard))

    async def handle_callback(self, update, context):
        query = update.callback_query
        await query.answer()

        if query.data == "cancel":
            await query.edit_message_text("Cancelled.")
            return

        if not query.data.startswith("download_"):
            return

        parts = query.data.split("_", 2)
        if len(parts) != 3:
            return

        format_type, url = parts[1], parts[2]
        chat_id = update.effective_chat.id

        download_message = await query.edit_message_text(f"Starting {format_type} download...")
        await self._download_and_send(url, chat_id, format_type, download_message, context)

    async def _download_and_send(self, url, chat_id, format_type, message, context):
        """Download and send file"""
        try:
            file_path = await self.downloader.download_video(url, chat_id, format_type, message)
            if not file_path:
                await message.edit_text("Download failed.")
                return

            file_size = os.path.getsize(file_path)
            max_size = self.config['telegram']['max_file_size_mb'] * 1024 * 1024

            if file_size > max_size:
                await message.edit_text(f"File too large ({file_size / 1024 / 1024:.1f}MB). Max: {self.config['telegram']['max_file_size_mb']}MB")
                os.unlink(file_path)
                return

            file_size_mb = file_size / (1024 * 1024)
            await message.edit_text(f"Uploading ({file_size_mb:.1f} MB)...")

            with open(file_path, 'rb') as f:
                if format_type == 'audio':
                    await context.bot.send_audio(chat_id=chat_id, audio=f)
                else:
                    await context.bot.send_video(chat_id=chat_id, video=f)

            await message.edit_text(f"Completed. Size: {file_size_mb:.1f} MB")
            os.unlink(file_path)
            self.downloader.cleanup_old_files()

        except Exception as e:
            self.logger.error(f"Download error: {e}")
            await message.edit_text("Download failed.")

    def run(self):
        self.logger.info("Starting Telegram bot...")
        self.downloader.cleanup_old_files()
        self.app.run_polling()


def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Telegram Video Downloader Bot')
    parser.add_argument('-c', '--config',
                       default=Path(__file__).parent.parent / "config.toml",
                       type=Path,
                       help='Path to configuration file (default: config.toml)')
    parser.add_argument('-d', '--downloads',
                       type=Path,
                       help='Downloads directory (overrides config file setting)')

    args = parser.parse_args()
    config_path = args.config

    if not config_path.exists():
        print(f"Error: Configuration file not found at {config_path}")
        return 1

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = toml.load(f)
    except Exception as e:
        print(f"Error loading configuration: {e}")
        return 1

    # Override downloads directory if specified via CLI
    if args.downloads:
        config['download']['output_dir'] = str(args.downloads)

    if not config.get('telegram', {}).get('bot_token'):
        print("Error: telegram.bot_token is required in config.toml")
        return 1

    if config['telegram']['bot_token'] == "YOUR_BOT_TOKEN_HERE":
        print("Error: Please set your actual bot token in config.toml")
        return 1

    bot = TelegramBot(config)

    try:
        bot.run()
    except KeyboardInterrupt:
        print("\nBot stopped by user")
    except Exception as e:
        print(f"Bot error: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
