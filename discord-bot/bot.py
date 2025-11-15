"""
This file initializes the Discord bot and loads all it's Cogs.

Project: LSU FSAE Discord Bot
Author: Khan Sumer / LSUTigerRacing
"""

import os
import asyncio
import logging
from pathlib import Path

import discord
from discord.ext import commands
from dotenv import load_dotenv

# Logging Configuration 
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# Directory Setup for universal deployment
ROOT_DIR = Path(__file__).resolve().parent 
COGS_DIR = ROOT_DIR / "bot" / "cogs"

# ENV / Discord Token Loading
load_dotenv(dotenv_path=ROOT_DIR / ".env")
TOKEN = os.getenv("TOKEN") 
if not TOKEN:
    raise ValueError("No TOKEN found in .env file")

# Bot Permissions (Adjust as needed for future updates)
intents = discord.Intents.default()


class FSAEBot(commands.Bot):
    """
    Custom bot class that automatically loads all Cogs
    and manages startup/shutdown behavior.
    """

    def __init__(self):
        # Initializes bot without any command prefixes (Changeable, but slash commands are superior)
        super().__init__(command_prefix=None, intents=intents)

    async def setup_hook(self):
        """
        Runs before the bot connects to Discord.
        Loads all .py Cog files from /bot/cogs
        """
        if not COGS_DIR.exists():
            logger.warning(f"Cogs Directory Not Found: {COGS_DIR}")
            return
        
        for filename in COGS_DIR.iterdir():
            # Skips private/special files (e.g., __init__.py)
            if filename.name.endswith('.py') and not filename.name.startswith('_'):
                extension = f"bot.cogs.{filename.stem}"
                try:
                    await self.load_extension(extension)
                    logger.info(f'Loaded Cog: {filename}')
                except Exception:
                    logger.error(f"Failed to load Cog: {filename}", exc_info=True)

    async def on_ready(self):
        """
        Called once the bot is connected to Discord and ready.
        Syncs slash commands and confirms successful startup.
        """
        logger.info(f'Logged in as {self.user}')
        await self.tree.sync()
        logger.info("Slash commands synced.")
    
    async def close(self):
        """
        Safely shuts down the bot.
        """
        logger.info("Shutting down FSAE Bot...")
        await super().close()    

async def main():
    """
    Handles startup, safe shutdown, and error catching.
    """
    bot = FSAEBot()

    try:
        await bot.start(TOKEN)
    except KeyboardInterrupt:
        logger.info("Bot manually stopped via keyboard interrupt")
    except Exception:
        logger.critical("Fatal error occurred while running bot", exc_info=True)
    finally:
        await bot.close()

if __name__ == '__main__':
    # Starts the asynchronous loop
    asyncio.run(main())