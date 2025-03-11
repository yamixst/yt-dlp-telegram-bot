#!/usr/bin/env python3
"""
Telegram Bot for downloading videos using yt-dlp
"""

import asyncio
import logging
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse

import aiofiles
import toml
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)


class VideoDownloader:
    def __init__(self, config: Dict):
        self.config = config
        self.download_dir = Path(config['download']['output_dir'])
        self.download_dir.mkdir(parents=True, exist_ok=True)

        # Active downloads tracking
        self.active_downloads: Dict[int, Dict] = {}

        # Setup logging
        logging.basicConfig(
            format=config['logging']['format'],
            level=getattr(logging, config['logging']['level'])
        )
        self.logger = logging.getLogger(__name__)

    def is_supported_url(self, url: str) -> bool:
        """Check if URL is from supported site"""
        try:
            domain = urlparse(url).netloc.lower()

            # Check each supported site
            for site, enabled in self.config['supported_sites'].items():
                if not enabled:
                    continue

                if site == 'youtube' and ('youtube.com' in domain or 'youtu.be' in domain):
                    return True
                elif site == 'vimeo' and 'vimeo.com' in domain:
                    return True
                elif site == 'dailymotion' and 'dailymotion.com' in domain:
                    return True
                elif site == 'twitch' and 'twitch.tv' in domain:
                    return True
                elif site == 'tiktok' and 'tiktok.com' in domain:
                    return True
                elif site == 'instagram' and 'instagram.com' in domain:
                    return True
                elif site == 'twitter' and ('twitter.com' in domain or 'x.com' in domain):
                    return True
                elif site == 'reddit' and 'reddit.com' in domain:
                    return True

            return False
        except Exception:
            return False

    def _get_download_format(self, url: str, format_type: str) -> str:
        """Get appropriate format string based on URL and format type"""
        domain = urlparse(url).netloc.lower()

        if format_type == 'audio':
            return 'bestaudio'

        # Use simpler format for Instagram to avoid compatibility issues
        if 'instagram.com' in domain:
            return 'best'

        # Use configured format for other sites
        return f"{self.config['download']['quality']}/best/worst"

    async def get_video_info(self, url: str) -> Optional[Dict]:
        """Get video information using yt-dlp"""
        try:
            cmd = [
                'yt-dlp',
                '--dump-json',
                '--no-playlist',
                url
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                self.logger.error(f"yt-dlp info error: {stderr.decode()}")
                return None

            import json
            info = json.loads(stdout.decode())

            # Calculate estimated file size
            duration = info.get('duration', 0)
            filesize = info.get('filesize') or info.get('filesize_approx')
            estimated_size_mb = None

            if filesize:
                estimated_size_mb = filesize / (1024 * 1024)
            elif duration:
                # Rough estimate: ~1MB per minute for compressed video
                estimated_size_mb = duration / 60

            return {
                'title': info.get('title', 'Unknown'),
                'duration': info.get('duration', 0),
                'uploader': info.get('uploader', 'Unknown'),
                'view_count': info.get('view_count', 0),
                'upload_date': info.get('upload_date', ''),
                'description': info.get('description', '')[:200] + '...' if info.get('description', '') else '',
                'estimated_size_mb': estimated_size_mb,
            }

        except Exception as e:
            self.logger.error(f"Error getting video info: {e}")
            return None

    async def download_video(self, url: str, chat_id: int, format_type: str = 'video', status_message=None) -> Optional[str]:
        """Download video using yt-dlp"""
        try:
            # Create unique filename
            timestamp = int(time.time())
            output_template = str(self.download_dir / f"{chat_id}_{timestamp}_%(title)s.%(ext)s")

            # Prepare command based on format type with fallback options
            cmd = ['yt-dlp']

            if format_type == 'audio':
                cmd.extend([
                    '--extract-audio',
                    '--audio-format', self.config['download']['audio_format'],
                    '--audio-quality', '0',
                ])
            else:
                # Get appropriate format based on site
                format_str = self._get_download_format(url, format_type)
                # Use fallback format options for better compatibility
                fallback_quality = f"{self.config['download']['quality']}/best/worst"
                cmd.extend([
                    '--format', fallback_quality,
                    '--merge-output-format', self.config['download']['video_format'],
                ])

            cmd.extend([
                '--output', output_template,
                '--no-playlist',
                '--no-check-certificates',  # Help with some sites
                '--progress-template', '%(progress.downloaded_bytes)s/%(progress.total_bytes)s %(progress.speed)s',
                url
            ])

            self.logger.info(f"Starting download: {' '.join(cmd)}")

            # Track download
            self.active_downloads[chat_id] = {
                'url': url,
                'start_time': time.time(),
                'format': format_type
            }

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            # Monitor progress if status_message is provided
            if status_message:
                asyncio.create_task(self._monitor_download_progress(process, status_message, chat_id))

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self.config['limits']['download_timeout_seconds']
            )

            # Remove from active downloads
            self.active_downloads.pop(chat_id, None)

            if process.returncode != 0:
                error_msg = stderr.decode()
                self.logger.error(f"Download error: {error_msg}")

                # Try fallback with simpler format if original failed
                if "Requested format is not available" in error_msg and format_type == 'video':
                    self.logger.info("Retrying with simpler format...")
                    return await self._retry_with_simple_format(url, chat_id, output_template)

                return None

            # Find downloaded file
            pattern = f"{chat_id}_{timestamp}_*"
            files = list(self.download_dir.glob(pattern))

            if files:
                return str(files[0])

            return None

        except asyncio.TimeoutError:
            self.logger.error("Download timeout")
            self.active_downloads.pop(chat_id, None)
            return None

        except Exception as e:
            self.logger.error(f"Download error: {e}")
            self.active_downloads.pop(chat_id, None)
            return None

    async def _monitor_download_progress(self, process, status_message, chat_id):
        """Monitor download progress and update status message"""
        # Check if progress tracking is enabled
        if not self.config['download'].get('show_download_progress', True):
            return

        try:
            last_update = 0
            update_count = 0
            update_interval = max(2, self.config['download'].get('progress_update_interval_seconds', 3))
            threshold_bytes = self.config['download'].get('progress_update_threshold_kb', 512) * 1024

            while process.returncode is None:
                await asyncio.sleep(update_interval)

                # Check if download directory has new files for this chat
                pattern = f"{chat_id}_*"
                files = list(self.download_dir.glob(pattern))

                if files:
                    # Get the largest (most recent) file
                    current_file = max(files, key=lambda f: f.stat().st_size)
                    current_size = current_file.stat().st_size

                    # Only update if size changed significantly
                    if current_size - last_update > threshold_bytes:
                        last_update = current_size
                        size_mb = current_size / (1024 * 1024)
                        update_count += 1

                        # Add dots animation for visual feedback
                        dots = "." * (update_count % 4)

                        try:
                            await status_message.edit_text(f"Downloading{dots} {size_mb:.1f} MB")
                        except Exception:
                            # Ignore telegram API errors (too many requests, etc)
                            pass

                await asyncio.sleep(1)

        except Exception as e:
            self.logger.error(f"Progress monitoring error: {e}")

    async def _retry_with_simple_format(self, url: str, chat_id: int, output_template: str) -> Optional[str]:
        """Retry download with simpler format options"""
        try:
            cmd = [
                'yt-dlp',
                '--format', 'best',  # Simple best format
                '--output', output_template,
                '--no-playlist',
                '--no-check-certificates',
                url
            ]

            self.logger.info(f"Retry download: {' '.join(cmd)}")

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self.config['limits']['download_timeout_seconds']
            )

            if process.returncode != 0:
                self.logger.error(f"Retry download failed: {stderr.decode()}")
                return None

            # Find downloaded file
            pattern = f"{chat_id}_*"
            files = list(self.download_dir.glob(pattern))

            if files:
                return str(files[0])

            return None

        except Exception as e:
            self.logger.error(f"Retry download error: {e}")
            return None



    def cleanup_old_files(self):
        """Clean up old downloaded files"""
        try:
            cutoff_time = time.time() - (self.config['limits']['cleanup_after_hours'] * 3600)

            for file_path in self.download_dir.glob("*"):
                if file_path.is_file() and file_path.stat().st_mtime < cutoff_time:
                    file_path.unlink()
                    self.logger.info(f"Cleaned up old file: {file_path}")

        except Exception as e:
            self.logger.error(f"Cleanup error: {e}")


class TelegramBot:
    def __init__(self, config: Dict):
        self.config = config
        self.downloader = VideoDownloader(config)
        self.logger = logging.getLogger(__name__)

        # Create application
        self.app = Application.builder().token(config['telegram']['bot_token']).build()

        # Add handlers
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CommandHandler("status", self.status_command))
        self.app.add_handler(CommandHandler("cleanup", self.cleanup_command))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_url))
        self.app.add_handler(CallbackQueryHandler(self.handle_callback))

    def is_chat_allowed(self, chat_id: int) -> bool:
        """Check if chat is allowed to use the bot"""
        allowed_chats = self.config['telegram']['allowed_chat_ids']
        return not allowed_chats or chat_id in allowed_chats

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        if not self.is_chat_allowed(update.effective_chat.id):
            await update.message.reply_text("Not authorized.")
            return

        welcome_text = (
            "Video Downloader Bot\n\n"
            "Send me a video URL.\n\n"
            "Supported sites:\n"
        )

        for site, enabled in self.config['supported_sites'].items():
            if enabled:
                welcome_text += f"- {site.title()}\n"

        welcome_text += "\nUse /help for more information"

        await update.message.reply_text(welcome_text)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        if not self.is_chat_allowed(update.effective_chat.id):
            return

        auto_threshold = self.config['download'].get('auto_download_video_under_minutes', 0)

        help_text = (
            "How to use:\n"
            "1. Send video URL\n"
        )

        if auto_threshold > 0:
            help_text += f"2. Videos < {auto_threshold} min: auto-download as video\n"
            help_text += "3. Longer videos: choose format\n"
        else:
            help_text += "2. Choose format (video/audio)\n"

        help_text += (
            "\nCommands:\n"
            "/start - Start\n"
            "/help - Help\n"
            "/status - Downloads\n"
            "/cleanup - Clean files\n\n"
            "Limits:\n"
            f"Max size: {self.config['telegram']['max_file_size_mb']}MB\n"
            f"Max duration: {self.config['download']['max_duration_minutes']} minutes\n"
            f"Max concurrent: {self.config['limits']['max_concurrent_downloads']}"
        )

        await update.message.reply_text(help_text)

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command"""
        if not self.is_chat_allowed(update.effective_chat.id):
            return

        active = len(self.downloader.active_downloads)

        if active == 0:
            await update.message.reply_text("No active downloads")
            return

        status_text = f"Active downloads: {active}\n\n"

        for chat_id, info in self.downloader.active_downloads.items():
            elapsed = int(time.time() - info['start_time'])
            status_text += f"Chat {chat_id}: {info['format']} ({elapsed}s)\n"

        await update.message.reply_text(status_text)

    async def cleanup_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /cleanup command"""
        if not self.is_chat_allowed(update.effective_chat.id):
            return

        await update.message.reply_text("Starting cleanup...")

        try:
            old_count = len(list(self.downloader.download_dir.glob("*")))
            self.cleanup_files()
            new_count = len(list(self.downloader.download_dir.glob("*")))
            cleaned = old_count - new_count

            await update.message.reply_text(f"Cleanup completed. Removed {cleaned} files.")
        except Exception as e:
            self.logger.error(f"Cleanup command error: {e}")
            await update.message.reply_text("Cleanup failed.")

    async def handle_url(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle URL messages"""
        if not self.is_chat_allowed(update.effective_chat.id):
            await update.message.reply_text("Not authorized.")
            return

        url = update.message.text.strip()
        chat_id = update.effective_chat.id

        # Check if URL is supported
        if not self.downloader.is_supported_url(url):
            await update.message.reply_text("URL not supported.")
            return

        # Check concurrent downloads limit
        if len(self.downloader.active_downloads) >= self.config['limits']['max_concurrent_downloads']:
            await update.message.reply_text(f"Max downloads ({self.config['limits']['max_concurrent_downloads']}) reached.")
            return

        # Check if user already has active download
        if chat_id in self.downloader.active_downloads:
            await update.message.reply_text("Download in progress.")
            return

        # Get video info
        status_message = await update.message.reply_text("Getting info...")

        video_info = await self.downloader.get_video_info(url)



        if not video_info:
            await status_message.edit_text("Could not get video info.")
            return

        # Check duration limit
        duration_minutes = video_info.get('duration', 0) / 60
        if duration_minutes > self.config['download']['max_duration_minutes']:
            await status_message.edit_text(
                f"Video too long ({duration_minutes:.1f} min). Max: {self.config['download']['max_duration_minutes']} min."
            )
            return

        # Check if video is short enough for auto-download
        auto_download_threshold = self.config['download'].get('auto_download_video_under_minutes', 0)

        if auto_download_threshold > 0 and duration_minutes < auto_download_threshold:
            # Auto-download as video for short videos
            size_info = ""
            if video_info.get('estimated_size_mb'):
                size_info = f"Size: {video_info['estimated_size_mb']:.1f} MB\n"

            await status_message.edit_text(
                f"{video_info['title']}\n"
                f"Duration: {duration_minutes:.1f} min\n"
                f"{size_info}"
                f"Downloading..."
            )

            # Start video download directly
            try:
                file_path = await self.downloader.download_video(url, chat_id, 'video', status_message)

                if not file_path:
                    await status_message.edit_text("Download failed.")
                    return

                # Check file size
                file_size = os.path.getsize(file_path)
                max_size = self.config['telegram']['max_file_size_mb'] * 1024 * 1024

                if file_size > max_size:
                    await status_message.edit_text(
                        f"File too large ({file_size / 1024 / 1024:.1f}MB). Max: {self.config['telegram']['max_file_size_mb']}MB"
                    )
                    os.unlink(file_path)
                    return

                # Send file
                await status_message.edit_text("Uploading...")

                with open(file_path, 'rb') as f:
                    await context.bot.send_video(
                        chat_id=chat_id,
                        video=f
                    )

                # Show final file size
                final_size_mb = file_size / (1024 * 1024)
                await status_message.edit_text(f"Completed. Size: {final_size_mb:.1f} MB")

                # Clean up file
                os.unlink(file_path)

                # Run cleanup after successful download
                self.cleanup_files()

            except Exception as e:
                self.logger.error(f"Auto-download error: {e}")
                await status_message.edit_text("Download failed.")
        else:
            # Show video info and format options for longer videos
            size_info = ""
            if video_info.get('estimated_size_mb'):
                size_info = f"Size: {video_info['estimated_size_mb']:.1f} MB\n"

            info_text = (
                f"{video_info['title']}\n"
                f"Duration: {duration_minutes:.1f} min\n"
                f"{size_info}"
            )

            keyboard = [
                [
                    InlineKeyboardButton("Video", callback_data=f"download_video_{url}"),
                    InlineKeyboardButton("Audio", callback_data=f"download_audio_{url}")
                ],
                [InlineKeyboardButton("Cancel", callback_data="cancel")]
            ]

            await status_message.edit_text(
                info_text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle callback queries"""
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

        format_type = parts[1]  # video or audio
        url = parts[2]
        chat_id = update.effective_chat.id

        # Start download
        download_message = await query.edit_message_text(f"Starting {format_type} download...")

        try:
            file_path = await self.downloader.download_video(url, chat_id, format_type, download_message)

            if not file_path:
                await download_message.edit_text("Download failed.")
                return

            # Check file size
            file_size = os.path.getsize(file_path)
            max_size = self.config['telegram']['max_file_size_mb'] * 1024 * 1024

            if file_size > max_size:
                await download_message.edit_text(
                    f"File too large ({file_size / 1024 / 1024:.1f}MB). Max: {self.config['telegram']['max_file_size_mb']}MB"
                )
                os.unlink(file_path)
                return

            # Send file
            file_size_mb = file_size / (1024 * 1024)
            await download_message.edit_text(f"Uploading ({file_size_mb:.1f} MB)...")

            with open(file_path, 'rb') as f:
                if format_type == 'audio':
                    await context.bot.send_audio(
                        chat_id=chat_id,
                        audio=f
                    )
                else:
                    await context.bot.send_video(
                        chat_id=chat_id,
                        video=f
                    )

            # Show final file size in completion message
            await download_message.edit_text(f"Completed. Size: {file_size_mb:.1f} MB")

            # Clean up file
            os.unlink(file_path)

            # Run cleanup after successful download
            self.cleanup_files()

        except Exception as e:
            self.logger.error(f"Download error: {e}")
            await download_message.edit_text("Download failed.")

    def cleanup_files(self):
        """Clean up old files on demand"""
        try:
            self.downloader.cleanup_old_files()
            self.logger.info("File cleanup completed")
        except Exception as e:
            self.logger.error(f"Cleanup error: {e}")

    def run(self):
        """Run the bot"""
        self.logger.info("Starting Telegram bot...")

        # Run initial cleanup
        self.cleanup_files()

        # Run bot
        self.app.run_polling()


def main():
    """Main entry point"""
    # Load configuration
    config_path = Path(__file__).parent.parent / "config.toml"

    if not config_path.exists():
        print(f"Error: Configuration file not found at {config_path}")
        print("Please create config.toml with your settings.")
        return 1

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = toml.load(f)
    except Exception as e:
        print(f"Error loading configuration: {e}")
        return 1

    # Validate required settings
    if not config.get('telegram', {}).get('bot_token'):
        print("Error: telegram.bot_token is required in config.toml")
        return 1

    if config['telegram']['bot_token'] == "YOUR_BOT_TOKEN_HERE":
        print("Error: Please set your actual bot token in config.toml")
        return 1

    # Create and run bot
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
