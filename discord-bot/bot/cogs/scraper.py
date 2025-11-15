"""
FSAE Ruleset Scraper Cog
---------------------------------------------

This cog periodically scrapes the official Formula SAE (FSAE) website for new or updated
rule PDFs under the "Ruleset and Resources" section. When changes are detected, the bot
announces them in a designated Discord channel with proper role mentions.

Main Features:
- Automated scraping using Playwright and BeautifulSoup
- Change detection using cached JSON data (fsae_pdfs.json)
- Fetches metadata via HTTP HEAD requests
- Sends formatted announcements to a designated discord channel with role tagging
"""

import asyncio
import os
import json
import logging
import discord
from discord.ext import commands, tasks
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from pathlib import Path
import aiohttp
from pathlib import Path

logger = logging.getLogger(__name__)

# Path to the JSON cache storing previously scraped PDFs for comparison
ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_FILE = ROOT_DIR / "fsae_pdfs.json"

class ScraperCog(commands.Cog):
    """Cog that handles automated scraping and Discord announcements for FSAE ruleset updates."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.check_for_updates.start()
    
    def save_data(self, data):
        """Save the current list of PDFs to the local JSON cache file."""
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

    def load_data(self):
        """Load the most recently saved list of PDFs, or return an empty list if none exists."""
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return []
    
    async def get_metadata(self, url: str, session: aiohttp.ClientSession):
        """
        Fetch metadata for a given PDF via a HEAD request.
        Used mainly to obtain the filename from Content-Disposition headers.
        """
        try:
            async with session.head(url) as response:
                filename = None
                disposition = response.headers.get("Content-Disposition")
                if disposition:
                    for part in disposition.split(';'):
                        if part.strip().startswith('filename='):
                            filename = part.split('=')[1].strip()
                return {"filename": filename}
        except Exception as e:
            logger.error(f"Could not fetch metadata for {url}: {e}", exc_info=True)
            return {"filename": None}

    @tasks.loop(seconds=20)
    async def check_for_updates(self):
        """Periodically scrapes the site, compares results, and announces any new or modified PDFs."""
        previous_pdfs = self.load_data()
        current_pdfs = await self.scrape_pdfs()

        # Attach filenames via metadata requests
        async with aiohttp.ClientSession() as session:
            for pdf in current_pdfs:
                metadata = await self.get_metadata(pdf['url'], session)
                pdf['filename'] = metadata.get('filename')

        previous_urls = {pdf['url']: pdf for pdf in previous_pdfs}
        previous_titles = {pdf['title']: pdf for pdf in previous_pdfs}

        new_pdfs = []
        modified_pdfs = []

        # Compare current scrape with previous data to detect changes
        for pdf in current_pdfs:
            if pdf['url'] in previous_urls:
                previous_pdf = previous_urls[pdf['url']]
                # Detect file changes based on filename or document ID (with same title)
                if (
                    pdf['filename'] != previous_pdf.get('filename') 
                    or (pdf['document_id'] != previous_pdf.get('document_id') and pdf['title'] == previous_pdf.get('title'))
                ):
                    modified_pdfs.append(pdf)
            elif pdf['title'] in previous_titles:
                # Title match but new URL means likely modified document
                modified_pdfs.append(pdf)
            else:
                new_pdfs.append(pdf)
        
        CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
        ROLE_ID = int(os.getenv("ROLE_ID"))
        if not CHANNEL_ID or not ROLE_ID:
            logger.warning("CHANNEL_ID or ROLE_ID not set in env file. Skipping announcements.")
            return

        # Announces any new or modified PDFs found
        if new_pdfs or modified_pdfs:
            channel = self.bot.get_channel(CHANNEL_ID)
            if not channel:
                return
            
            if new_pdfs:
                logger.info(f"--- Found {len(new_pdfs)} new documents in 'Ruleset and Resources': ---")
                message_parts = []
                message_parts.append(f"<@&{ROLE_ID}> **New FSAE Rules Posted:**\n")
                for pdf in new_pdfs:
                    message_parts.append(f"> **{pdf['title']}:**\n> {pdf['url']}")
                await channel.send("\n".join(message_parts))
                
            if modified_pdfs:
                logger.info(f"--- Found {len(modified_pdfs)} modified documents in 'Ruleset and Resources': ---")
                message_parts = []
                message_parts.append(f"<@&{ROLE_ID}> **FSAE Rules Have Been Updated:**\n")
                for pdf in modified_pdfs:
                    message_parts.append(f"> **{pdf['title']}:** **(Updated)**\n> {pdf['url']}")
                await channel.send("\n".join(message_parts))
        else:
            logger.info("--- No new or modified documents found. ---")
        
        # Saves the latest data for next comparison
        self.save_data(current_pdfs)

    @check_for_updates.before_loop
    async def before_check(self):
        """Ensures the bot is fully ready before starting the periodic scrape."""
        await self.bot.wait_until_ready()
        await asyncio.sleep(5) # optional but recommended safety buffer
        logger.info("Bot is ready, starting the first scrape check.")

    async def scrape_pdfs(self):
        """Scrape the FSAE website for all PDFs listed under 'Ruleset and Resources'."""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto("https://www.fsaeonline.com/cdsweb/gen/DocumentResources.aspx")
            html = await page.content()
            await browser.close()

        soup = BeautifulSoup(html, "html.parser")
        ruleset_row = soup.find("tr", {"data-folder-id": "Ruleset and Resources"})
        if not ruleset_row:
            logger.warning("Ruleset row not found")
            return
        
        # Collect all sibling rows until the next folder section
        rows = []
        for sibling in ruleset_row.find_next_siblings("tr"):
            # Stops after hitting the next folder section
            if "folder" in sibling.get("class", []):
                break
            rows.append(sibling)
        
        links = []
        base_url = "https://www.fsaeonline.com"

        for row in rows:
            # Finds the document title (usually in the first cell)
            first_cell = row.find("td")
            main_title = first_cell.find(text=True, recursive=False).strip()

            # Finds any description text
            desc_tag = first_cell.find("span")
            desc_text = desc_tag.get_text(strip=True) if desc_tag else ""
            
            # Creates the final title and adds any description text 
            final_title = main_title
            if desc_text:
                final_title += f" ({desc_text})"

            # Find the download button specifically
            download_tag = row.find("a", class_="btn btn-primary")

            # Checks that a valid download button was found
            if download_tag and "href" in download_tag.attrs:
                download_url = download_tag["href"]
                full_url = base_url + download_url

                # Extracts DocumentID from URL if present
                try:
                    doc_id = full_url.split("DocumentID=")[1]
                except IndexError:
                    doc_id = None
                
                links.append({
                    "title": final_title, 
                    "url": full_url,
                    "document_id": doc_id
                })

        return links

async def setup(bot: commands.Bot):
    """Adds the ScraperCog to the bot."""
    await bot.add_cog(ScraperCog(bot))