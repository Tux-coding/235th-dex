#=================================================================
# IMPORTS
#=================================================================
import random
import logging
import os
import asyncio
import signal
import json
import time
import aiohttp
import datetime
import shutil

from typing import List
from collections import Counter
from aiohttp import client_exceptions

import discord # type: ignore
from discord import app_commands
from discord.ext import commands, tasks # type: ignore
from discord.ui import Button, View, Modal, TextInput #type:ignore 
from dotenv import load_dotenv # type: ignore //please ensure that you have python-dotenv installed (command is "pip install python-dotenv")

# Import the cards list from cards.py
from cards import cards

#=================================================================
# CONFIG & GLOBALS
#=================================================================
  
# Configuring logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s:%(levelname)s:%(name)s: %(message)s')

# Loading environment variables
load_dotenv()
token = os.getenv('DISCORD_TOKEN')
channel_ids_str = os.getenv('CHANNEL_IDS', '')
channel_ids = [id.strip() for id in channel_ids_str.split(',') if id.strip()]
test_channel_id = os.getenv('TEST_CHANNEL_ID')
spawn_mode = os.getenv('SPAWN_MODE', 'both').lower()

missing_vars = []
if not token:
    missing_vars.append('DISCORD_TOKEN')
if not channel_ids:
    missing_vars.append("CHANNEL_IDS")
if not test_channel_id:
    missing_vars.append("TEST_CHANNEL_ID")

if missing_vars:
    logging.error(f"Missing required environment variables: {', '.join(missing_vars)}")
    exit(1)

try:
    [int(channel_id) for channel_id in channel_ids]
    int(test_channel_id)
except ValueError:
    logging.error("Channel IDs must be valid integers")
    exit(1)

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Global state variables
player_cards = {}
last_spawned_card_per_channel = {}
spawned_messages = []
allowed_guilds = [int(test_channel_id)] + [int(channel_id) for channel_id in channel_ids]
battle_lock = asyncio.Lock()
trade_lock = asyncio.Lock()
submit_lock = asyncio.Lock()
is_test_mode = spawn_mode == 'test'
blacklist_file = "blacklist.json"
start_time = datetime.datetime.now()
user_stats = {}
trade_stats = {}

backup_folder = "backup_folder"
os.makedirs(backup_folder, exist_ok=True)
MAX_BACKUPS = 6

authorized_user_ids = os.getenv('AUTHORIZED_USER_IDS', '').split(',')
authorized_user_ids = [user_id.strip() for user_id in authorized_user_ids if user_id.strip().isdigit()]
logging.info(f"Authorized user IDs loaded.")

#=================================================================
# UTILITY FUNCTIONS
#=================================================================
def is_authorized(ctx):
    return str(ctx.author.id) in authorized_user_ids

def validate_recipient(ctx, recipient):
    if not recipient:
        raise commands.UserInputError("Please specify a user. Usage: `/[command] @user`")
    
    if recipient.id == ctx.author.id:
        raise commands.UserInputError("You can't use this command on yourself!")

    if recipient.bot:
        raise commands.UserInputError("You can't use this command on a bot!")
    
    return True

def requires_valid_user():
    async def predicate(ctx):
        recipient = None
        for param_name, param in ctx.command.clean_params.items():
            if param.annotation == discord.Member:
                index = list(ctx.command.clean_params.keys()).index(param_name)
                if len(ctx.args) > index + 1:
                    recipient = ctx.args[index + 1]
                break
        
        if recipient and isinstance(recipient, discord.Member):
            return validate_recipient(ctx, recipient)
        return True

    return commands.check(predicate)

def weighted_random_choice(cards: list[dict]) -> dict:
    total = sum(card['rarity'] for card in cards)
    r = random.uniform(0, total)
    upto = 0
    for card in cards:
        upto += card['rarity']
        if upto >= r:
            return card
    return None

def user_has_card(user_id: str, card_name: str) -> bool:
    card_name = card_name.lower()
    for card in player_cards.get(user_id, []):
        card_aliases = next((c.get('aliases', []) for c in cards if c['name'].lower() == card.lower()), [])
        if card_name == card.lower() or card_name in [alias.lower() for alias in card_aliases]:
            return True
    return False

def validate_card_data():
    """Validate that all cards have required fields"""
    required_fields = ['name', 'health', 'attack', 'rarity', 'spawn_image_url', 'card_image_url', 'aliases']
    for i, card in enumerate(cards):
        missing_fields = [field for field in required_fields if field not in card]
        if missing_fields:
            logging.warning(f"Card #{i} ({card.get('name', 'Unknown')}) is missing fields: {', '.join(missing_fields)}")
        
        # Check for valid URLs
        for url_field in ['spawn_image_url', 'card_image_url']:
            if url_field in card and not card[url_field].startswith(('http://', 'https://')):
                logging.warning(f"Card {card.get('name', 'Unknown')} has invalid {url_field}: {card[url_field]}")

def get_spawn_channels():
    """Get the appropriate channels based on spawn mode"""
    channels = []
    
    if spawn_mode in ['both', 'test']:
        test_channel = bot.get_channel(int(test_channel_id))
        if test_channel:
            channels.append(test_channel)
        else:
            logging.error(f"Test channel {test_channel_id} not found.")
    
    if spawn_mode == 'both':
        for channel_id in channel_ids:
            channel = bot.get_channel(int(channel_id))
            if channel:
                channels.append(channel)
            else:
                logging.error(f"Channel {channel_id} not found.")
    
    return channels

def select_random_card(exclude_card_name=None):
    """Select a random card, optionally excluding a specific card name."""
    available_cards = [card for card in cards if card['name'] != exclude_card_name] if exclude_card_name else cards
    if not available_cards:
        return random.choice(cards)  # fallback, should not happen
    return weighted_random_choice(available_cards)

def count_lines_of_code() -> int:
    project_dir = os.path.dirname(os.path.abspath(__file__))
    total_lines_of_code = 0

    for root, _, files in os.walk(project_dir):
        for file in files:
            if file.endswith('test.py') or file.endswith('cards.py'):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        total_lines_of_code += sum(1 for _ in f)
                except Exception as e:
                    logging.error(f"Error counting lines in {file_path}: {e}")
    return total_lines_of_code

async def send_embed_with_retry(channel, embed, view=None, retries=3, delay=2):
    """Send an embed with retry logic for network errors"""
    for attempt in range(retries):
        try:
            if view:
                return await channel.send(embed=embed, view=view)
            else:
                return await channel.send(embed=embed)
        except discord.HTTPException as e:
            if attempt < retries - 1:
                logging.warning(f"HTTP error when sending embed to {channel.id}, attempt {attempt+1}/{retries}: {e}")
                await asyncio.sleep(delay * (2 ** attempt))
            else:
                logging.error(f"Failed to send embed after {retries} attempts: {e}")
                raise
        except aiohttp.ClientConnectionError as e:
            logging.error(f"Connection error when sending embed: {e}")
            if attempt < retries - 1:
                await asyncio.sleep(delay * 3)
            else:
                raise
        except Exception as e:
            logging.error(f"Unexpected error sending embed: {e}")
            raise

def update_user_stats(user_id: str, stat_type: str, value: int = 1):
    """Update user statistics tracking"""
    if user_id not in user_stats:
        user_stats[user_id] = {
            'battles_fought': 0,
            'battles_won': 0,
            'trades_completed': 0,
            'cards_caught': 0
        }
    user_stats[user_id][stat_type] += value

def update_trade_stats(card_name: str):
    """Update card trade statistics"""
    if card_name not in trade_stats:
        trade_stats[card_name] = 0
    trade_stats[card_name] += 1
#=================================================================
# DATA MANAGEMENT
#=================================================================
# Blacklist management
class BlacklistManager:
    @staticmethod
    def load_blacklist() -> List[str]:
        try:
            with open(blacklist_file, "r") as f:
                data = f.read().strip()
                if not data:
                    return []
                return json.loads(data)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logging.error(f"Error loading blacklist: {e}")
            return []

    @staticmethod
    def save_blacklist(blacklist: List[str]) -> None:
        try:
            with open(blacklist_file, "w") as f:
                json.dump(blacklist, f)
        except Exception as e:
            logging.error(f"Error saving blacklist: {e}")

    @staticmethod
    def is_blacklisted(user_id: str) -> bool:
        blacklist = BlacklistManager.load_blacklist()
        return user_id in blacklist
    
    @staticmethod
    def add_to_blacklist(user_id: str) -> bool:
        blacklist = BlacklistManager.load_blacklist()
        if user_id in blacklist:
            return False
        blacklist.append(user_id)
        BlacklistManager.save_blacklist(blacklist)
        return True
    
    @staticmethod
    def remove_from_blacklist(user_id: str) -> bool:
        blacklist = BlacklistManager.load_blacklist()
        if user_id not in blacklist:
            return False
        blacklist.remove(user_id)
        BlacklistManager.save_blacklist(blacklist)
        return True

def load_player_cards() -> None:
    global player_cards
    try:
        logging.info(f"Cards loaded: {len(cards)} cards")
        if os.path.exists('player_cards.json') and os.path.getsize('player_cards.json') > 0:
            with open('player_cards.json', 'r', encoding='utf-8') as f:
                player_cards = json.load(f)
            # Ensure all keys are strings
            player_cards = {str(k): v for k, v in player_cards.items()}
            logging.info("Player cards loaded successfully: %d users found", len(player_cards))
        else:
            # Create a new file if it doesn't exist or is empty
            player_cards = {}
            logging.info("Player cards file is empty or doesn't exist. Creating a new file.")
            save_player_cards()  # Save the empty dictionary to create the file
    except json.JSONDecodeError as e:
        logging.error(f"Error decoding JSON from player cards file: {e}")
        recover_from_backup()
    except Exception as e:
        logging.error(f"Unexpected error loading player cards: {e}")
        recover_from_backup()

def save_player_cards() -> None:
    max_retries = 3

    for attempt in range(max_retries):
        try:
            temp_file = 'player_cards_temp.json'
            with open(temp_file, 'w') as f:
                json.dump(player_cards, f, indent=4)

            shutil.move(temp_file, 'player_cards.json')
            return
        except PermissionError:
            if attempt < max_retries - 1:
                logging.warning(f"Permission denied when saving player cards. Retry {attempt + 1}/{max_retries}...")
                time.sleep(2)  # Wait before retrying
            else:
                logging.error("Persistent permission denied when saving player cards after multiple attempts")
                emergency_path = f'player_cards_emergency_{int(time.time())}.json'
                try:
                    with open(emergency_path, 'w') as f:
                        json.dump(player_cards, f, indent=4)
                    logging.info(f"Created emergency backup at {emergency_path}")
                except Exception as e:
                    logging.error(f"Failed to create emergency backup: {e}")
        except OSError as e:
            logging.error(f"OS error when saving player cards: {e}")
            if "No space left on device" in str(e):
                logging.critical("Disk space issue detected when saving player data!")
                try:
                    with open('player_cards_minimal.json', 'w') as f:
                        json.dump(player_cards, f)
                except Exception as e2:
                    logging.error(f"Failed even minimal save: {e2}")
            time.sleep(1)
        except Exception as e:
            logging.error(f"Error saving player cards: {e}")
            break  # Exit on non-permission errors

def recover_from_backup():
    global player_cards
    backup_files = [f for f in os.listdir(backup_folder) if f.startswith("player_cards_backup_")]
    if backup_files:
        latest_backup = max(backup_files)
        backup_path = os.path.join(backup_folder, latest_backup)
        logging.info(f"Attempting to recover from backup: {backup_path}")
        try:
            with open(backup_path, 'r', encoding='utf-8') as f:
                player_cards = json.load(f)
            player_cards = {str(k): v for k, v in player_cards.items()}
            logging.info("Recovery successful")
            save_player_cards()  # Save the recovered data back to the main file
        except Exception as backup_error:
            logging.error(f"Backup recovery failed: {backup_error}")
            player_cards = {}
    else:
        logging.error("No backups found. Starting with an empty dictionary.")
        player_cards = {}

def create_backup():
    try:
        if not os.path.exists(backup_folder):
            os.makedirs(backup_folder)
            logging.info(f"Created backup folder: {backup_folder}")

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"player_cards_backup_{timestamp}.json"
        backup_filepath = os.path.join(backup_folder, backup_filename)
        shutil.copy('player_cards.json', backup_filepath)
        logging.info(f"Created backup: {backup_filename} in {backup_filepath}")

        backup_files = [f for f in os.listdir(backup_folder) if f.startswith("player_cards_backup_")]
        backup_files.sort(key=lambda f: os.path.getmtime(os.path.join(backup_folder, f)))

        if len(backup_files) > MAX_BACKUPS:
            for old_file in backup_files[:-MAX_BACKUPS]:
                old_filepath = os.path.join(backup_folder, old_file)
                os.remove(old_filepath)
                logging.info(f"Removed old backup: {old_file}")
    except Exception as e:
        logging.error(f"Failed to create backup: {e}")

@tasks.loop(hours=8)
async def backup_player_data():
    logging.info("Running scheduled backup of player data")
    try:
        create_backup()
        logging.info("Backup completed successfully")
    except Exception as e:
        logging.error(f"Backup failed: {e}", exc_info=True)

async def card_name_autocomplete(
    interaction: discord.Interaction,
    current: str
) -> list[app_commands.Choice[str]]:
    """Autocomplete for cards the user owns, filtered by input."""
    user_id = str(interaction.user.id)
    user_cards = player_cards.get(user_id, [])
    # Remove duplicates and filter by current input
    filtered = [
        card for card in set(user_cards)
        if current.lower() in card.lower()
    ]
    # Limit to 25 choices (Discord API limit)
    return [
        app_commands.Choice(name=card, value=card)
        for card in filtered[:25]
    ]

#=================================================================
# UI COMPONENTS
#=================================================================
# Catch System UI
class CatchModal(Modal):
    def __init__(self, card_name, view, message):
        super().__init__(title="Catch the Card")
        self.card_name = card_name
        self.view = view
        self.message = message
        self.card_input = TextInput(label="Card Name", placeholder="Type the card name here")
        self.add_item(self.card_input)

    async def on_submit(self, interaction: discord.Interaction):
        global submit_lock
        user = interaction.user
        user_id = str(user.id)

        # Attempt to acquire the lock with a timeout of 5 seconds
        try:
            acquired = await asyncio.wait_for(submit_lock.acquire(), timeout=5.0)
            if not acquired:
                await interaction.response.send_message("Unable to process your request. Please try again.", ephemeral=True)
                return
        except asyncio.TimeoutError:
            await interaction.response.send_message("The system is busy. Please try again in a moment.", ephemeral=True)
            return
        
        # Use try-finally to ensure lock is released even if an error occurs
        try:
            if self.view.card_claimed:
                await interaction.response.send_message("The card has already been claimed.", ephemeral=True)
                return

            input_name = self.card_input.value.lower()
            if input_name == self.card_name.lower() or input_name in [alias.lower() for alias in next(card['aliases'] for card in cards if card['name'].lower() == self.card_name.lower())]:
                user_id = str(user.id)
                player_cards.setdefault(user_id, []).append(self.card_name)
                save_player_cards()
                update_user_stats(user_id, 'cards_caught')
                await interaction.response.send_message(f"{user.mention} caught the card: {self.card_name}!", ephemeral=False)
                self.view.card_claimed = True
                for item in self.view.children:
                    if isinstance(item, Button):
                        item.disabled = True
                await self.message.edit(view=self.view)
            else:
                await interaction.response.send_message(f"{user.mention}; Incorrect name.", ephemeral=False)
        finally:
            submit_lock.release()

class CatchButton(Button):
    def __init__(self, card_name):
        super().__init__(label="Catch the card", style=discord.ButtonStyle.primary)
        self.card_name = card_name

    async def callback(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        if is_test_mode and user_id not in authorized_user_ids:
            await interaction.response.send_message("We are currently updating the bot, please wait until we are finished.", ephemeral=True)
            return
        
        if BlacklistManager.is_blacklisted(str(interaction.user.id)) and user_id not in authorized_user_ids:
            await interaction.response.send_message("You are blacklisted and cannot use this bot.", ephemeral=True)
            return
        
        user = interaction.user
        modal = CatchModal(self.card_name, self.view, interaction.message)
        await interaction.response.send_modal(modal)

class CatchView(View):
    def __init__(self, card_name):
        super().__init__(timeout=None)
        self.card_claimed = False
        self.add_item(CatchButton(card_name))

# Progress View UI
class ProgressView(View):
    def __init__(self, user_cards, missing_cards, user, display_name_override=None):
        super().__init__(timeout=None)
        self.user_cards = user_cards  
        self.unique_user_cards = list(set(user_cards))
        self.missing_cards = missing_cards
        self.user = user
        self.display_name_override = display_name_override  # NEW
        self.current_page = 0
        self.viewing_owned = True

        card_counts = Counter(self.user_cards)
        self.rarity_zero_cards = [card for card in card_counts if next((c for c in cards if c['name'] == card), {}).get('rarity', 100) == 0]
        self.other_cards = [card for card in card_counts if card not in self.rarity_zero_cards]

        self.owned_pages = max(1, (len(self.other_cards) + 9) // 10)
        self.missing_pages = max(1, (len(self.missing_cards) + 9) // 10)
        self.total_pages = self.owned_pages + self.missing_pages

        self.update_buttons()

    def create_embed(self):
        if self.viewing_owned:
            return self.create_owned_embed()
        else:
            return self.create_missing_embed()
    
    def update_buttons(self):
        self.clear_items()
        
        # First page button (only show if not on first page)
        if self.current_page > 0:
            first_button = Button(label="First Page", style=discord.ButtonStyle.secondary, emoji="⏮️")
            first_button.callback = self.first_page
            self.add_item(first_button)
        
        # Previous page button (only show if not on first page)
        if self.current_page > 0:
            prev_button = Button(label="Previous", style=discord.ButtonStyle.primary, emoji="⬅️")
            prev_button.callback = self.previous_page
            self.add_item(prev_button)
        
        # Toggle between owned and missing cards
        toggle_label = "View Missing Cards" if self.viewing_owned else "View Owned Cards"
        toggle_button = Button(label=toggle_label, style=discord.ButtonStyle.secondary, emoji="🔄")
        toggle_button.callback = self.toggle_view
        self.add_item(toggle_button)
        
        # Next page button (only show if not on last page)
        if (self.viewing_owned and self.current_page < self.owned_pages - 1) or \
           (not self.viewing_owned and self.current_page < self.missing_pages - 1):
            next_button = Button(label="Next", style=discord.ButtonStyle.primary, emoji="➡️")
            next_button.callback = self.next_page
            self.add_item(next_button)
        
        # Last page button (only show if not on last page)
        current_max_pages = self.owned_pages if self.viewing_owned else self.missing_pages
        if self.current_page < current_max_pages - 1:
            last_button = Button(label="Last Page", style=discord.ButtonStyle.secondary, emoji="⏭️")
            last_button.callback = self.last_page
            self.add_item(last_button)

    async def toggle_view(self, interaction: discord.Interaction):
        if interaction.user != self.user:
            await interaction.response.send_message("You can't control this menu, sorry!", ephemeral=True)
            return
            
        self.viewing_owned = not self.viewing_owned
        self.current_page = 0  # Reset to first page when toggling view
        self.update_buttons()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    async def first_page(self, interaction: discord.Interaction):
        if interaction.user != self.user:
            await interaction.response.send_message("You can't control this menu, sorry!", ephemeral=True)
            return
            
        self.current_page = 0
        self.update_buttons()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    async def previous_page(self, interaction: discord.Interaction):
        if interaction.user != self.user:
            await interaction.response.send_message("You can't control this menu, sorry!", ephemeral=True)
            return
            
        self.current_page -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    async def next_page(self, interaction: discord.Interaction):
        if interaction.user != self.user:
            await interaction.response.send_message("You can't control this menu, sorry!", ephemeral=True)
            return
            
        self.current_page += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)
        
    async def last_page(self, interaction: discord.Interaction):
        if interaction.user != self.user:
            await interaction.response.send_message("You can't control this menu, sorry!", ephemeral=True)
            return
        
        # Set to last page based on current view
        if self.viewing_owned:
            self.current_page = self.owned_pages - 1
        else:
            self.current_page = self.missing_pages - 1
            
        self.update_buttons()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)
            
    def create_owned_embed(self):
        display_name = self.display_name_override if self.display_name_override else self.user.display_name
        embed = discord.Embed(
            title="📚 Card Collection Progress",
            description=f"Showing {display_name}'s owned unique cards ({len(set(self.unique_user_cards))}/{len(set(self.unique_user_cards)) + len(self.missing_cards)} unique cards collected)",
            color=discord.Color.green()
        )
        card_counts = Counter(self.user_cards)
        start = self.current_page * 10
        end = min(start + 10, len(self.other_cards))

        if self.current_page == 0 and self.rarity_zero_cards:
            rarity_zero_section = "**OG Cards (Rarity 0%)**\n" + "\n".join(
                [f"\u2022 {card} x{card_counts[card]}" if card_counts[card] > 1 else f"\u2022 {card}" for card in self.rarity_zero_cards]
            )
            embed.add_field(name="🌟 OG Cards", value=rarity_zero_section, inline=False)

        if self.other_cards:
            owned_cards = "\n".join(
                [f"\u2022 {card} x{card_counts[card]}" if card_counts[card] > 1 else f"\u2022 {card}" for card in self.other_cards][start:end]
            )
            embed.add_field(name="📋 Your Cards", value=owned_cards, inline=False)
        else:
            if not (self.current_page == 0 and self.rarity_zero_cards):
                embed.add_field(name="📋 Your Cards", value="You don't have any cards yet.", inline=False)

        embed.set_footer(text=f"Page {self.current_page + 1}/{self.owned_pages} (Owned Cards) • Use buttons to navigate")
        return embed
            
    def create_missing_embed(self):
        embed = discord.Embed(
            title="📚 Card Collection Progress",
            description=f"Showing missing cards ({len(self.missing_cards)} remaining)",
            color=discord.Color.red()
        )
        
        start = self.current_page * 10
        end = min(start + 10, len(self.missing_cards))
        
        if self.missing_cards:
            missing_cards = "\n".join([f"• {card}" for card in self.missing_cards[start:end]])
            embed.add_field(name="❓ Missing Cards", value=missing_cards, inline=False)
        else:
            embed.add_field(name="❓ Missing Cards", value="You've collected all cards! Congratulations!", inline=False)
        
        embed.set_footer(text=f"Page {self.current_page + 1}/{self.missing_pages} (Missing Cards) • Use buttons to navigate")
        return embed
    
# Trade System UI
class TradeSession:
    def __init__(self, ctx, initiator, recipient):
        self.ctx = ctx
        self.initiator = initiator
        self.recipient = recipient
        self.initiator_id = str(initiator.id)
        self.recipient_id = str(recipient.id)
        self.initiator_cards: List[str] = []
        self.recipient_cards: List[str] = []
        self.initiator_confirmed = False
        self.recipient_confirmed = False
        self.trade_message = None
        self.timeout = 180
        self.last_activity = time.time()
        self.active = True

    def reset_activity_timer(self):
        """Reset the activity timer whenever a user performs an action"""
        self.last_activity = time.time()

    async def start_trade(self):
        embed = discord.Embed(
            title="📦 Card Trade Initiated",
            description=f"{self.initiator.mention} wants to trade with {self.recipient.mention}!\n\n"
                      f"Both players can select cards to offer in the trade.",
            color=discord.Color.gold()
        )
        embed.set_footer(text=f"Trade will expire after {self.timeout} seconds of inactivity.")

        view = TradeInviteView(self)
        self.trade_message = await self.ctx.send(embed=embed, view=view)

        asyncio.create_task(self.monitor_timeout())

    async def monitor_timeout(self):
        """Monitor for inactivity timeout"""
        while self.active:
            await asyncio.sleep(10)
            if time.time() - self.last_activity > self.timeout:
                await self.cancel_trade("Trade expired due to inactivity.")

                if hasattr(bot, 'active_trades'):
                    if self.initiator_id in bot.active_trades:
                        del bot.active_trades[self.initiator_id]
                    if self.recipient_id in bot.active_trades:
                        del bot.active_trades[self.recipient_id]
                return

    async def update_trade_status(self):
        """Update the trade status embed"""
        if not self.active:
            return
        
        def format_card_with_rarity(card_name):
            card_data = next((c for c in cards if c['name'] == card_name), None)
            if not card_data:
                return card_name
            rarity = card_data.get('rarity', 100)
            if rarity == 0:
                return f"**{card_name}** 🌟"
            elif rarity < 5:
                return f"{card_name} 🌟"
            elif rarity < 10:
                return f"{card_name} ⭐"
            else:
                return card_name
    
        initiator_cards_str = "None" if not self.initiator_cards else ", ".join(
            [format_card_with_rarity(card) for card in self.initiator_cards])
        recipient_cards_str = "None" if not self.recipient_cards else ", ".join(
            [format_card_with_rarity(card) for card in self.recipient_cards])
        
        embed = discord.Embed(
            title="📦 Trade in Progress",
            description=f"Trade between {self.initiator.mention} and {self.recipient.mention}",
            color=discord.Color.gold()
        )

        embed.add_field(
            name=f"{self.initiator.display_name}'s Offer:" + (" ✅" if self.initiator_confirmed else ""),
            value=initiator_cards_str,
            inline=False
        )
        embed.add_field(
            name=f"{self.recipient.display_name}'s Offer:" + (" ✅" if self.recipient_confirmed else ""),
            value=recipient_cards_str,
            inline=False
        )

        embed.add_field(
            name="Instructions",
            value="• Use `/trade add [card]` to add cards to your offer\n"
                  "• Use `/trade remove [card]` to remove cards\n"
                  "• Use `/trade confirm` when you're satisfied with the deal\n"
                  "• Use `/trade cancel` to cancel the trade",
            inline=False
        )

        try:
            new_message = await self.ctx.send(embed=embed)
            self.trade_message = new_message
        except Exception as e:
            logging.error(f"Error updating trade status: {e}")

    async def finalize_trade(self):
        """Complete the trade by exchanging cards"""
        async with trade_lock:
            for card in self.initiator_cards:
                if not user_has_card(self.initiator_id, card):
                    await self.cancel_trade(f"{self.initiator.mention} no longer has the card `{card}`.")
                    return

            for card in self.recipient_cards:
                if not user_has_card(self.recipient_id, card):
                    await self.cancel_trade(f"{self.recipient.mention} no longer has the card `{card}`.")
                    return
            
            embed = discord.Embed(
                title="🔍 Final Trade Confirmation",
                description=f"Please review this trade one last time:",
                color=discord.Color.gold()
            )

            embed.add_field(
                name=f"{self.initiator.display_name} will give:",
                value=", ".join(self.initiator_cards) if self.initiator_cards else "Nothing",
                inline=True
            )

            embed.add_field(
                name=f"{self.recipient.display_name} will give:",
                value=", ".join(self.recipient_cards) if self.recipient_cards else "Nothing",
                inline=True
            )

            embed.set_footer(text="Trade will complete in 20 seconds. Type /trade cancel to stop.")

            await self.ctx.send(embed=embed)

            self.finalization_time = time.time()
            await asyncio.sleep(20)  # Allow 20 seconds for final confirmation

            if not self.active:
                return

            try:
                for card in self.initiator_cards:
                    player_cards[self.initiator_id].remove(card)
                    player_cards.setdefault(self.recipient_id, []).append(card)
                    update_trade_stats(card)

                for card in self.recipient_cards:
                    player_cards[self.recipient_id].remove(card)
                    player_cards.setdefault(self.initiator_id, []).append(card)
                    update_trade_stats(card)
                
                update_user_stats(self.initiator_id, 'trades_completed')
                update_user_stats(self.recipient_id, 'trades_completed')

                save_player_cards()

                embed = discord.Embed(
                    title="🎉 Trade Completed!",
                    description="Cards have been successfully exchanged.",
                    color=discord.Color.green()
                )
                
                initiator_summary = "None" if not self.initiator_cards else ", ".join(self.initiator_cards)
                recipient_summary = "None" if not self.recipient_cards else ", ".join(self.recipient_cards)
                
                embed.add_field(
                    name=f"{self.initiator.display_name} gave:",
                    value=initiator_summary,
                    inline=True
                )
                embed.add_field(
                    name=f"{self.recipient.display_name} gave:",
                    value=recipient_summary,
                    inline=True
                )
                
                await self.ctx.send(embed=embed)
                
                logging.info(f"Trade completed between {self.initiator.name} and {self.recipient.name}")

                self.active = False
                
            except Exception as e:
                logging.error(f"Error during trade finalization: {e}", exc_info=True)
                await self.ctx.send("An error occurred during the trade. Please try again later.")
                self.active = False

    async def cancel_trade(self, reason="Trade cancelled."):
        """Cancel the trade"""
        if not self.active:
            return
            
        self.active = False
        embed = discord.Embed(
            title="❌ Trade Cancelled",
            description=reason,
            color=discord.Color.red()
        )
        await self.ctx.send(embed=embed)

        try:
            if hasattr(self.trade_message, 'edit'):
                view = TradeInviteView(self)
                for child in view.children:
                    child.disabled = True
                await self.trade_message.edit(view=view)
        except Exception as e:
            logging.error(f"Error disabling trade buttons: {e}")

        if hasattr(bot, 'active_trades'):
            bot.active_trades.pop(self.initiator_id, None)
            bot.active_trades.pop(self.recipient_id, None)

class TradeInviteView(View):
    def __init__(self, trade_session):
        super().__init__(timeout=None)
        self.trade_session = trade_session

    @discord.ui.button(label="Accept Trade", style=discord.ButtonStyle.green)
    async def accept_trade(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.trade_session.recipient.id:
            await interaction.response.send_message("This trade invitation isn't for you!", ephemeral=True)
            return
        
        # Reset activity timer
        self.trade_session.reset_activity_timer()
        
        # Disable buttons
        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)
        
        # Show trade accepted message
        await interaction.response.send_message(f"{interaction.user.mention} has accepted the trade invitation!")
        
        # Update trade status
        await self.trade_session.update_trade_status()

    @discord.ui.button(label="Decline Trade", style=discord.ButtonStyle.red)
    async def decline_trade(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Allow both initiator and recipient to decline
        user_id = interaction.user.id
        if user_id == self.trade_session.recipient.id:
            await interaction.response.send_message("You declined the trade.", ephemeral=True)
            await self.trade_session.cancel_trade(f"{interaction.user.mention} declined the trade.")
        elif user_id == self.trade_session.initiator.id:
            # Show confirmation dialog for initiator
            await interaction.response.send_message(
                "Are you sure you want to cancel this trade?",
                view=DeclineConfirmView(self.trade_session, interaction.user),
                ephemeral=True
            )
        else:
            await interaction.response.send_message("This trade invitation isn't for you!", ephemeral=True)

class DeclineConfirmView(View):
    def __init__(self, trade_session, user):
        super().__init__(timeout=30)
        self.trade_session = trade_session
        self.user = user

    @discord.ui.button(label="Yes, cancel trade", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("This confirmation isn't for you!", ephemeral=True)
            return
        await interaction.response.send_message("You cancelled the trade.", ephemeral=True)
        await self.trade_session.cancel_trade(f"{self.user.mention} (initiator) cancelled the trade.")

    @discord.ui.button(label="No, keep trade", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("This confirmation isn't for you!", ephemeral=True)
            return
        await interaction.response.send_message("Trade not cancelled.", ephemeral=True)
        self.stop()

# Battle System UI
class CardBattle:
    def __init__(self, ctx, challenger, opponent):
        self.ctx = ctx
        self.challenger = challenger
        self.opponent = opponent
        self.challenger_id = str(challenger.id)
        self.opponent_id = str(opponent.id)
        self.challenger_cards = []
        self.opponent_cards = []
        self.challenger_selected = False
        self.opponent_selected = False
        self.battle_message = None
        self.timeout = 120
        self.last_activity = time.time()
        self.is_slash = isinstance(ctx, discord.Interaction)
    
    async def send_message(self, content=None, **kwargs):
        if self.is_slash:
            if not self.ctx.response.is_done():
                await self.ctx.response.send_message(content=content, **kwargs)
                return await self.ctx.original_response()
            return await self.ctx.followup.send(content=content, **kwargs)
        else:
            return await self.ctx.send(content=content, **kwargs)
    
    def reset_activity_timer(self):
        """Reset the activity timer whenever a user performs an action"""
        self.last_activity = time.time()

    async def start_battle(self):
        embed = discord.Embed(
            title="Card Battle!",
            description=f"{self.challenger.mention} has challenged {self.opponent.mention} to a card battle!\n\n"
                        f"Each player will select up to 3 cards to battle with.\n"
                        f"Cards will take turns attacking until one side has no cards left.",
            color=discord.Color.gold()
        )
        embed.set_footer(text=f"Players have {self.timeout} seconds to select cards. Timer resets with each action.")

        view = BattleInviteView(self)
        self.battle_message = await self.send_message(embed=embed, view=view)

        # Wait for acceptance and card selection
        selection_complete = await self.wait_for_selection()
        
        # If wait_for_selection returns False, we timed out
        if not selection_complete:
            # Disable the view buttons when timing out
            for child in view.children:
                child.disabled = True
            await self.battle_message.edit(view=view)
            await self.send_message("Battle invitation timed out due to inactivity.")
            return
        
        # Both players have selected cards, begin the battle
        if self.challenger_selected and self.opponent_selected:
            # Send a "preparing battle" message
            await self.send_message(f"Both players have selected their cards! Preparing for battle...")
            await asyncio.sleep(2)  # Short dramatic pause
            await self.execute_battle()
        else:
            # This should not happen due to the wait_for_selection, but just in case
            await self.send_message("Battle cancelled.")
    
    async def wait_for_selection(self):
        """Wait until both players have selected their cards or timeout occurs"""
        while not (self.challenger_selected and self.opponent_selected):
            # Check if we've exceeded timeout since last activity
            if time.time() - self.last_activity > self.timeout:
                return False  # Timed out
            await asyncio.sleep(1)
        return True  # Both players selected cards

    async def execute_battle(self):
        # Initialize battle state
        challenger_battle_cards = [self._copy_card_for_battle(card) for card in self.challenger_cards]
        opponent_battle_cards = [self._copy_card_for_battle(card) for card in self.opponent_cards]

        # Battle announcement
        embed = discord.Embed(
            title="A battle has started!",
            description=f"{self.challenger.mention} vs {self.opponent.mention}",
            color=discord.Color.dark_red()
        )

        # Show selected cards
        challenger_cards_str = "\n".join([f"• **{card['name']}** (❤️ {card['health']}, ⚔️ {card['attack']})" 
                                        for card in challenger_battle_cards])
        opponent_cards_str = "\n".join([f"• **{card['name']}** (❤️ {card['health']}, ⚔️ {card['attack']})" 
                                    for card in opponent_battle_cards])
        
        embed.add_field(name=f"{self.challenger.display_name}'s Team:", value=challenger_cards_str, inline=True)
        embed.add_field(name=f"{self.opponent.display_name}'s Team:", value=opponent_cards_str, inline=True)
        
        battle_log = await self.ctx.send(embed=embed)

        # Battle loop
        turn = 0
        battle_log_text = []

        while challenger_battle_cards and opponent_battle_cards:
            turn += 1 
            await asyncio.sleep(2)  # Dramatic pause between turns

            # Determine attacker and defender based on turn
            if turn % 2 == 1:  # Challenger's turn
                attacker_name = self.challenger.display_name
                defender_name = self.opponent.display_name
                attacker_cards = challenger_battle_cards
                defender_cards = opponent_battle_cards
            else:  # Opponent's turn
                attacker_name = self.opponent.display_name
                defender_name = self.challenger.display_name
                attacker_cards = opponent_battle_cards
                defender_cards = challenger_battle_cards

            # Select random cards for attack/defense
            attacking_card = random.choice(attacker_cards)
            defending_card = random.choice(defender_cards)

            # Calculate damage with a chance for critical hit
            crit_chance = 0.25
            crit_multiplier = 1.25
            damage = attacking_card['attack']
            
            if random.random() < crit_chance:
                damage = int(damage * crit_multiplier)
                log_entry = f"**Turn {turn}:** {attacker_name}'s **{attacking_card['name']}** lands a CRITICAL HIT on {defender_name}'s **{defending_card['name']}** for {damage} damage!"
            else:
                log_entry = f"**Turn {turn}:** {attacker_name}'s **{attacking_card['name']}** attacks {defender_name}'s **{defending_card['name']}** for {damage} damage!"
            
            defending_card['health'] -= damage
            battle_log_text.append(log_entry)

            # Check if defending card is defeated
            if defending_card['health'] <= 0:
                log_entry = f"💥 {defender_name}'s **{defending_card['name']}** has been defeated!"
                battle_log_text.append(log_entry)
                defender_cards.remove(defending_card)

            # Update battle log (show last 10 actions)
            recent_log = "\n".join(battle_log_text[-10:])

            # Update the battle status embed
            status_embed = discord.Embed(
                title=f"⚔️ Battle: Turn {turn} ⚔️",
                description=recent_log,
                color=discord.Color.dark_red()
            )

            # Show current cards and their health
            if challenger_battle_cards:
                challenger_status = "\n".join([f"• **{card['name']}** (❤️ {card['health']})" for card in challenger_battle_cards])
            else:
                challenger_status = "*No cards left*"

            if opponent_battle_cards:
                opponent_status = "\n".join([f"• **{card['name']}** (❤️ {card['health']})" for card in opponent_battle_cards])
            else:
                opponent_status = "*No cards left*"

            status_embed.add_field(name=f"{self.challenger.display_name}'s Team:", value=challenger_status, inline=True)
            status_embed.add_field(name=f"{self.opponent.display_name}'s Team:", value=opponent_status, inline=True)
            
            await battle_log.edit(embed=status_embed)

        # Determine winner
        if not opponent_battle_cards:
            winner = self.challenger
            loser = self.opponent
            update_user_stats(self.challenger_id, 'battles_won')
        else:
            winner = self.opponent
            loser = self.challenger
            update_user_stats(self.opponent_id, 'battles_won')
        
        update_user_stats(self.challenger_id, 'battles_fought')
        update_user_stats(self.opponent_id, 'battles_fought')

        # Victory message
        victory_embed = discord.Embed(
            title="🏆 Battle Results 🏆",
            description=f"**{winner.display_name}** has defeated {loser.display_name} in battle!",
            color=discord.Color.gold()
        )
        await self.ctx.send(embed=victory_embed)

    def _copy_card_for_battle(self, card_name):
        original_card = next((c for c in cards if c['name'] == card_name), None)
        if original_card:
            return {
                'name': original_card['name'],
                'health': original_card['health'],
                'attack': original_card.get('attack', 1)
            }
        # Fallback in case the card isn't found
        return {
            'name': card_name,
            'health': 1,
            'attack': 1
        }
    
class BattleInviteView(View):
    def __init__(self, battle):
        super().__init__(timeout=battle.timeout)
        self.battle = battle
        
    @discord.ui.button(label="Accept Challenge", style=discord.ButtonStyle.green)
    async def accept_battle(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.battle.opponent.id:
            await interaction.response.send_message("This challenge isn't for you!", ephemeral=True)
            return
        
        # Reset activity timer when accept button is pressed
        self.battle.reset_activity_timer()
        
        # Send a public message that the challenge was accepted
        await self.battle.ctx.send(f"{interaction.user.mention} has accepted the battle challenge! Both players must select their cards to begin.")
        
        # Send card selection directly in channel with ephemeral message (only visible to opponent)
        user_cards = player_cards.get(str(interaction.user.id), [])
        unique_cards = list(set(user_cards))
        
        # Create card selection view for opponent
        view = CardSelectionView(self.battle, interaction.user, "opponent", unique_cards)
        embed = discord.Embed(
            title="Select Your Battle Cards",
            description="Choose up to 3 cards for battle.\nClick Submit when you're done.",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        
        # Also send selection to challenger (in a separate ephemeral message)
        challenger_cards = player_cards.get(self.battle.challenger_id, [])
        unique_challenger_cards = list(set(challenger_cards))
        
        # Create a new message for the challenger
        challenger_view = CardSelectionView(self.battle, self.battle.challenger, "challenger", unique_challenger_cards)
        challenger_embed = discord.Embed(
            title="Select Your Battle Cards",
            description="Choose up to 3 cards for battle.\nClick Submit when you're done.",
            color=discord.Color.blue()
        )
        
        # Send the challenger their own ephemeral message (only they can see it)
        await self.battle.ctx.send(
            content=f"{self.battle.challenger.mention}, choose your cards for battle!",
            embed=challenger_embed,
            view=challenger_view,
            ephemeral=True
        )
        
        # Disable the buttons
        for item in self.children:
            item.disabled = True
        
        await self.battle.battle_message.edit(view=self)
        
    @discord.ui.button(label="Decline Challenge", style=discord.ButtonStyle.red)
    async def decline_battle(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id == self.battle.opponent.id:
            # Opponent declining
            await interaction.response.send_message("You declined the battle.", ephemeral=True)
            await self.battle.ctx.send(f"{interaction.user.mention} declined the battle challenge.")
            
            # Disable the buttons
            for item in self.children:
                item.disabled = True
            await self.battle.battle_message.edit(view=self)
            
            # Clean up battle state
            if hasattr(bot, 'ongoing_battles'):
                bot.ongoing_battles.discard(self.battle.challenger_id)
                bot.ongoing_battles.discard(self.battle.opponent_id)
        
        elif interaction.user.id == self.battle.challenger.id:
            # Challenger declining - show confirmation dialog
            view = BattleCancelConfirmView(self.battle, interaction.user, self)
            await interaction.response.send_message(
                "Are you sure you want to cancel this battle challenge?",
                view=view,
                ephemeral=True
            )
        else:
            await interaction.response.send_message("This battle challenge isn't for you!", ephemeral=True)

class BattleCancelConfirmView(View):
    def __init__(self, battle, user, original_view):
        super().__init__(timeout=60)
        self.battle = battle
        self.user = user
        self.original_view = original_view

    @discord.ui.button(label="Yes, cancel battle", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("This confirmation isn't for you!", ephemeral=True)
            return

        await interaction.response.send_message("You cancelled the battle.", ephemeral=True)
        await self.battle.ctx.send(f"{self.user.mention} cancelled their battle challenge.")
        
        # Disable buttons in original view
        for item in self.original_view.children:
            item.disabled = True
        await self.battle.battle_message.edit(view=self.original_view)
        
        # Clean up battle state
        if hasattr(bot, 'ongoing_battles'):
            bot.ongoing_battles.discard(self.battle.challenger_id)
            bot.ongoing_battles.discard(self.battle.opponent_id)

    @discord.ui.button(label="No, keep battle", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("This confirmation isn't for you!", ephemeral=True)
            return
        
        await interaction.response.send_message("Battle challenge not cancelled.", ephemeral=True)
        self.stop()

class CardSelectionView(View):
    def __init__(self, battle, user, player_type, available_cards):
        super().__init__(timeout=battle.timeout)
        self.battle = battle
        self.user = user
        self.player_type = player_type  # "challenger" or "opponent"
        self.available_cards = available_cards
        self.selected_cards = []
        self.max_cards = 3
        self.selected_cards_text = ""
        
        # Add card selection dropdown
        self.add_item(CardSelectMenu(self))
        
        # Add card removal dropdown if needed
        self.remove_button = Button(
            label="Remove Card", 
            style=discord.ButtonStyle.red,
            disabled=True
        )
        self.remove_button.callback = self.remove_card
        self.add_item(self.remove_button)
    
    async def remove_card(self, interaction: discord.Interaction):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("This isn't your battle card selection!", ephemeral=True)
            return
        
        # Reset activity timer when removing a card
        self.battle.reset_activity_timer()
            
        if not self.selected_cards:
            await interaction.response.send_message("No cards to remove!", ephemeral=True)
            return
            
        # Create remove selection view
        remove_view = RemoveCardView(self)
        await interaction.response.send_message(
            "Select a card to remove:", 
            view=remove_view,
            ephemeral=True
        )
    
    @discord.ui.button(label="Submit Selection", style=discord.ButtonStyle.green)
    async def submit_cards(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("This isn't your battle card selection!", ephemeral=True)
            return
        
        # Reset activity timer when submitting cards
        self.battle.reset_activity_timer()
            
        if not self.selected_cards:
            await interaction.response.send_message("You must select at least one card!", ephemeral=True)
            return
        
        # Store the selected cards in the battle object
        if self.player_type == "challenger":
            self.battle.challenger_cards = self.selected_cards
            self.battle.challenger_selected = True
            waiting_for = "opponent"
            waiting_user = self.battle.opponent.display_name
        else:
            self.battle.opponent_cards = self.selected_cards
            self.battle.opponent_selected = True
            waiting_for = "challenger"
            waiting_user = self.battle.challenger.display_name
        
        # Confirmation message
        cards_list = ", ".join(self.selected_cards)
        
        # Disable all buttons in the view
        for item in self.children:
            item.disabled = True
            
        # Update the message to show we're waiting for the other player
        embed = discord.Embed(
            title="Battle Cards Selected",
            description=f"You've selected your cards and are ready for battle.\n\n**Your Cards:**\n{cards_list}",
            color=discord.Color.green()
        )
        
        # Add waiting message
        if not (self.battle.challenger_selected and self.battle.opponent_selected):
            embed.add_field(
                name="Waiting For", 
                value=f"Waiting for {waiting_user} to select their cards...",
                inline=False
            )
        
        try:
            # Try to update the message, but handle if it fails
            await interaction.response.edit_message(embed=embed, view=self)
        except discord.errors.NotFound:
            try:
                # If the message can't be found, send a new message
                await interaction.followup.send(
                    embed=embed,
                    ephemeral=True
                )
            except Exception as e:
                logging.error(f"Failed to send card selection confirmation: {e}")

class CardSelectMenu(discord.ui.Select):
    def __init__(self, parent_view):
        self.parent_view = parent_view
        
        # Create options from available cards
        options = []
        for i, card_name in enumerate(parent_view.available_cards[:25]):  # Discord limit of 25 options
            if i >= 25:  # Ensure we don't exceed Discord's limit
                break
                
            card_data = next((c for c in cards if c["name"] == card_name), None)
            if card_data:
                # Handle both 'damage' and 'attack' attributes for compatibility
                attack_value = card_data.get('attack', card_data.get('attack', 1))
                option = discord.SelectOption(
                    label=card_name[:25],  # Limit to 25 chars for label
                    description=f"HP: {card_data['health']} | ATK: {attack_value}",
                    value=card_name
                )
                options.append(option)
        
        # If no options, create a placeholder option
        if not options:
            options = [discord.SelectOption(label="No cards available", value="none")]
        
        super().__init__(
            placeholder="Select a card to add to your team...",
            min_values=1,
            max_values=1,
            options=options,
            disabled=len(options) == 1 and options[0].value == "none"
        )
    
    async def callback(self, interaction: discord.Interaction):
        # Verify this is the correct user
        if interaction.user.id != self.parent_view.user.id:
            await interaction.response.send_message("This isn't your battle card selection!", ephemeral=True)
            return
        
        # Reset activity timer when selecting a card
        self.parent_view.battle.reset_activity_timer()
            
        selected_card = self.values[0]
        
        if selected_card == "none":
            await interaction.response.send_message("You don't have any cards to select.", ephemeral=True)
            return
            
        # Add card if limit not reached
        if len(self.parent_view.selected_cards) < self.parent_view.max_cards:
            if selected_card not in self.parent_view.selected_cards:
                self.parent_view.selected_cards.append(selected_card)
                
                # Enable the remove button once cards are selected
                self.parent_view.remove_button.disabled = False
                
                # Update the current selection text
                self.parent_view.selected_cards_text = ", ".join(self.parent_view.selected_cards)
                
                # Create a new embed showing the current selection
                embed = discord.Embed(
                    title="Select Your Battle Cards",
                    description=f"Choose up to 3 cards for battle.\nClick Submit when you're done.\n\n**Current Selection:**\n{self.parent_view.selected_cards_text}",
                    color=discord.Color.blue()
                )
                
                # Update the message with the new embed and view
                try:
                    await interaction.response.edit_message(embed=embed, view=self.parent_view)
                except discord.errors.NotFound:
                    await interaction.followup.send("There was an error updating your selection. Please try again.", ephemeral=True)
            else:
                await interaction.response.send_message("You've already selected this card!", ephemeral=True)
        else:
            await interaction.response.send_message(f"You can only select {self.parent_view.max_cards} cards!", ephemeral=True)

class RemoveCardView(discord.ui.View):
    def __init__(self, parent_view):
        super().__init__(timeout=60)
        self.parent_view = parent_view
        
        # Add dropdown to select card to remove
        options = []
        for card in parent_view.selected_cards:
            options.append(discord.SelectOption(label=card, value=card))
            
        self.select = discord.ui.Select(
            placeholder="Select card to remove...",
            options=options
        )
        self.select.callback = self.remove_callback
        self.add_item(self.select)
    
    async def remove_callback(self, interaction: discord.Interaction):
        # Verify this is the correct user
        if interaction.user.id != self.parent_view.user.id:
            await interaction.response.send_message("This isn't your battle card selection!", ephemeral=True)
            return
        
        # Reset activity timer when removing a card
        self.parent_view.battle.reset_activity_timer()
            
        card_to_remove = self.select.values[0]
        if card_to_remove in self.parent_view.selected_cards:
            self.parent_view.selected_cards.remove(card_to_remove)
            
            # Update the selection text
            self.parent_view.selected_cards_text = ", ".join(self.parent_view.selected_cards)
            
            # Disable remove button if no cards left
            if not self.parent_view.selected_cards:
                self.parent_view.remove_button.disabled = True
            
            # Update the parent embed
            embed = discord.Embed(
                title="Select Your Battle Cards",
                description=f"Choose up to 3 cards for battle.\nClick Submit when you're done.\n\n**Current Selection:**\n{self.parent_view.selected_cards_text}",
                color=discord.Color.blue()
            )
            
            # Acknowledge the removal
            await interaction.response.send_message(f"Removed {card_to_remove} from your selection.", ephemeral=True)
            
            try:
                # Close this view
                await interaction.message.edit(view=None)
            except discord.errors.NotFound:
                # If message can't be found, just continue
                pass
            
            try:
                # Send a new ephemeral message with the updated card selection
                await interaction.followup.send(
                    embed=embed, 
                    view=self.parent_view,
                    ephemeral=True
                )
            except Exception as e:
                # If any other error occurs, try one more approach
                try:
                    await interaction.channel.send(
                        content=f"{self.parent_view.user.mention}, here's your updated card selection:",
                        embed=embed, 
                        view=self.parent_view,
                        ephemeral=True
                    )
                except Exception as e:
                    logging.error(f"Failed to send updated card selection: {e}")

class LeaderboardView(discord.ui.View):
    def __init__(self, ctx_or_interaction, initial_category="general"):
        super().__init__(timeout=60)
        self.ctx_or_interaction = ctx_or_interaction
        self.category = initial_category
        self.add_item(LeaderboardSelect(self, initial_category)) # godo

    async def update_leaderboard(self, interaction, category):
        embed = await get_leaderboard_embed(category)
        await interaction.response.edit_message(embed=embed, view=self)

class LeaderboardSelect(discord.ui.Select):
    def __init__(self, parent_view, initial_category):
        options = [
            discord.SelectOption(label="General", value="general", description="General statistics", default=initial_category=="general"),
            discord.SelectOption(label="Total Cards", value="total", description="Total cards leaderboard", default=initial_category=="total"),
            discord.SelectOption(label="Unique Cards", value="unique", description="Unique cards leaderboard", default=initial_category=="unique"),
            discord.SelectOption(label="Rarest Cards", value="rarest", description="Rarest cards and their owners", default=initial_category=="rarest"),
            discord.SelectOption(label="Activity", value="activity", description="Most active players", default=initial_category=="activity"),
            discord.SelectOption(label="Most Traded", value="traded", description="Most frequently traded cards", default=initial_category=="traded"),
            discord.SelectOption(label="Battles", value="battles", description="Battle champions", default=initial_category=="battles"),
        ]
        super().__init__(placeholder="Select leaderboard category...", min_values=1, max_values=1, options=options)
        self.parent_view = parent_view
    
    async def callback(self, interaction: discord.Interaction):
        self.parent_view.category = self.values[0]
        await self.parent_view.update_leaderboard(interaction, self.values[0])

async def get_leaderboard_embed(category: str):
    category = category.lower()
    # Skip authorized users from leaderboards
    regular_users = {user_id: cards_ for user_id, cards_ in player_cards.items() if user_id not in authorized_user_ids}
    total_users = len(regular_users)
    total_cards_collected = sum(len(cards_) for cards_ in regular_users.values())
    embed = None
    
    # Handle case when there are no cards yet
    if not regular_users or total_cards_collected == 0:
        embed = discord.Embed(
            title="235th Dex Statistics", 
            description="Not enough data to display statistics yet!",
            color=discord.Color.blue()
        )
        return embed
    
    if category == "general":
        # Top Collectors (by total cards)
        collectors = [(user_id, len(cards)) for user_id, cards in regular_users.items()]
        top_collectors = sorted(collectors, key=lambda x: x[1], reverse=True)[:5]
        
        # Unique Cards Leaderboard
        unique_collectors = [(user_id, len(set(cards))) for user_id, cards in regular_users.items()]
        top_unique_collectors = sorted(unique_collectors, key=lambda x: x[1], reverse=True)[:5]
        
        # Most Collected Card
        all_cards = [card for cards in regular_users.values() for card in cards]
        card_counts = Counter(all_cards)
        
        # Get most collected card (with safeguard if no cards exist)
        most_collected_card = card_counts.most_common(1)[0][0] if card_counts else "None"
        most_collected_count = card_counts.get(most_collected_card, 0)
        
        # Rarest Card Owned based on rarity value
        card_rarity = {card['name']: card['rarity'] for card in cards}
        unique_owned_cards = set(all_cards)
        
        if unique_owned_cards:
            try:
                rarest_card_owned = min(unique_owned_cards, key=lambda card: card_rarity.get(card, float('inf')))
                rarest_card_rarity = card_rarity.get(rarest_card_owned, "Unknown")
            except (ValueError, KeyError):
                rarest_card_owned = "Error determining rarest card"
                rarest_card_rarity = "Unknown"
        else:
            rarest_card_owned = "None"
            rarest_card_rarity = "N/A"
        
        embed = discord.Embed(
            title="📊 235th Dex Leaderboard",
            description="Global statistics for the card game",
            color=discord.Color.gold()
        )
        
        embed.add_field(
            name="📈 User Stats",
            value=f"**Total Players**: {total_users}\n**Total Cards Collected**: {total_cards_collected}",
            inline=False
        )
        
        # Top Collectors (format with card counts)
        if top_collectors:
            top_collectors_text = "\n".join([f"{idx+1}. <@{user_id}>: **{count}** cards" 
                                    for idx, (user_id, count) in enumerate(top_collectors)])
            embed.add_field(name="🏆 Top Collectors (Total Cards)", value=top_collectors_text, inline=True)
        else:
            embed.add_field(name="🏆 Top Collectors", value="No data yet", inline=True)
        
        # Top Unique Collectors
        if top_unique_collectors:
            unique_collectors_text = "\n".join([f"{idx+1}. <@{user_id}>: **{count}** unique cards" 
                                        for idx, (user_id, count) in enumerate(top_unique_collectors)])
            embed.add_field(name="🌟 Top Collectors (Unique Cards)", value=unique_collectors_text, inline=True)
        else:
            embed.add_field(name="🌟 Top Unique Collectors", value="No data yet", inline=True)
        
        # Card Stats section
        card_stats = [
            f"**Most Collected Card**: {most_collected_card} ({most_collected_count}× collected)",
            f"**Rarest Card Owned**: {rarest_card_owned} ({rarest_card_rarity}% rarity)"
        ]
        embed.add_field(name="🃏 Card Stats", value="\n".join(card_stats), inline=False)
    
    elif category == "total":
        # Total Cards Leaderboard (including duplicates)
        collectors = [(user_id, len(cards)) for user_id, cards in regular_users.items()]
        top_collectors = sorted(collectors, key=lambda x: x[1], reverse=True)[:10]
        
        embed = discord.Embed(
            title="🏆 Total Cards Leaderboard",
            description="Players ranked by total number of cards owned (including duplicates)",
            color=discord.Color.gold()
        )
        
        if top_collectors:
            leaderboard_text = ""
            for idx, (user_id, count) in enumerate(top_collectors):
                # Add medal emoji for top 3
                if idx == 0:
                    prefix = "🥇"
                elif idx == 1:
                    prefix = "🥈"
                elif idx == 2:
                    prefix = "🥉"
                else:
                    prefix = f"{idx+1}."
                
                leaderboard_text += f"{prefix} <@{user_id}>: **{count}** cards\n"
            
            embed.add_field(name="Leaderboard", value=leaderboard_text, inline=False)
        else:
            embed.add_field(name="Leaderboard", value="No data available yet", inline=False)
    
    elif category == "unique":
        # Unique Cards Leaderboard
        unique_collectors = [(user_id, len(set(cards))) for user_id, cards in regular_users.items()]
        top_unique = sorted(unique_collectors, key=lambda x: x[1], reverse=True)[:10]
        
        # Calculate completion percentage for each player
        total_available_cards = len(cards)
        completion_data = [(user_id, count, round((count / total_available_cards) * 100, 1)) 
                          for user_id, count in top_unique]
        
        embed = discord.Embed(
            title="🌟 Unique Cards Leaderboard",
            description=f"Players ranked by number of unique cards collected (out of {total_available_cards} total)",
            color=discord.Color.blue()
        )
        
        if top_unique:
            leaderboard_text = ""
            for idx, (user_id, count, percentage) in enumerate(completion_data):
                # Add medal emoji for top 3
                if idx == 0:
                    prefix = "🥇"
                elif idx == 1:
                    prefix = "🥈"
                elif idx == 2:
                    prefix = "🥉"
                else:
                    prefix = f"{idx+1}."
                
                leaderboard_text += f"{prefix} <@{user_id}>: **{count}** unique cards (**{percentage}%** complete)\n"
            
            embed.add_field(name="Leaderboard", value=leaderboard_text, inline=False)
        else:
            embed.add_field(name="Leaderboard", value="No data available yet", inline=False)
    
    elif category == "rarest":
        # Rarest Cards Leaderboard
        # First, get all card rarities
        card_rarity = {card['name']: card['rarity'] for card in cards}
        
        # Get the 10 rarest cards based on rarity value (lower is rarer)
        rarest_cards = sorted([(name, rarity) for name, rarity in card_rarity.items()], 
                             key=lambda x: x[1])[:10]
        
        # Find owners for each rare card
        rarest_cards_with_owners = []
        for card_name, rarity in rarest_cards:
            owners = []
            for user_id, user_cards in regular_users.items():
                if card_name in user_cards:
                    owners.append(user_id)
            rarest_cards_with_owners.append((card_name, rarity, owners))
        
        embed = discord.Embed(
            title="💎 Rarest Cards Leaderboard",
            description="The rarest cards and their lucky owners",
            color=discord.Color.purple()
        )
        
        if rarest_cards_with_owners:
            for idx, (card_name, rarity, owners) in enumerate(rarest_cards_with_owners):
                if owners:
                    # Limit the number of owners shown to prevent too long messages
                    displayed_owners = owners[:5]
                    owner_text = ", ".join([f"<@{owner}>" for owner in displayed_owners])
                    if len(owners) > 5:
                        owner_text += f" and {len(owners) - 5} more"
                else:
                    owner_text = "No owners yet"
                
                embed.add_field(
                    name=f"{idx+1}. {card_name} ({rarity}% rarity)",
                    value=f"**Owners**: {owner_text}",
                    inline=False
                )
        else:
            embed.add_field(name="Rarest Cards", value="No data available yet", inline=False)
    
    elif category == "activity":
        # Most Active Users Leaderboard
        # First check if user_stats exists and has data
        if not hasattr(bot, 'user_stats') or not user_stats:
            embed = discord.Embed(
                title="⚡ Activity Leaderboard",
                description="No activity data has been recorded yet!",
                color=discord.Color.orange()
            )
            return embed
        
        # Filter authorized users from stats
        filtered_stats = {user_id: stats for user_id, stats in user_stats.items() 
                         if user_id not in authorized_user_ids}
        
        # Calculate total activity score (sum of all activities)
        activity_scores = []
        for user_id, stats in filtered_stats.items():
            total_score = stats.get('battles_fought', 0) + stats.get('trades_completed', 0) + stats.get('cards_caught', 0)
            activity_scores.append((user_id, total_score, stats))
        
        # Sort by total activity score
        top_active_users = sorted(activity_scores, key=lambda x: x[1], reverse=True)[:10]
        
        embed = discord.Embed(
            title="⚡ Activity Leaderboard",
            description="Players ranked by their overall activity",
            color=discord.Color.orange()
        )
        
        if top_active_users:
            leaderboard_text = ""
            for idx, (user_id, score, stats) in enumerate(top_active_users):
                # Add medal emoji for top 3
                if idx == 0:
                    prefix = "🥇"
                elif idx == 1:
                    prefix = "🥈"
                elif idx == 2:
                    prefix = "🥉"
                else:
                    prefix = f"{idx+1}."
                
                battles = stats.get('battles_fought', 0)
                wins = stats.get('battles_won', 0)
                trades = stats.get('trades_completed', 0)
                cards = stats.get('cards_caught', 0)
                
                leaderboard_text += f"{prefix} <@{user_id}>: **{score}** points\n" \
                                   f"  ┣ Battles: {battles} ({wins} wins)\n" \
                                   f"  ┣ Trades: {trades}\n" \
                                   f"  ┗ Cards Caught: {cards}\n"
            
            embed.add_field(name="Most Active Players", value=leaderboard_text, inline=False)
        else:
            embed.add_field(name="Most Active Players", value="No activity data yet", inline=False)
    
    elif category == "traded":
        # Most Traded Cards Leaderboard
        # First check if trade_stats exists and has data
        if not hasattr(bot, 'trade_stats') or not trade_stats:
            embed = discord.Embed(
                title="🔄 Most Traded Cards",
                description="No trade data has been recorded yet!",
                color=discord.Color.teal()
            )
            return embed
        
        # Get top traded cards
        top_traded = sorted(trade_stats.items(), key=lambda x: x[1], reverse=True)[:10]
        
        embed = discord.Embed(
            title="🔄 Most Traded Cards",
            description="Cards that change hands most frequently",
            color=discord.Color.teal()
        )
        
        if top_traded:
            leaderboard_text = ""
            for idx, (card_name, count) in enumerate(top_traded):
                # Add medal emoji for top 3
                if idx == 0:
                    prefix = "🥇"
                elif idx == 1:
                    prefix = "🥈"
                elif idx == 2:
                    prefix = "🥉"
                else:
                    prefix = f"{idx+1}."
                
                leaderboard_text += f"{prefix} **{card_name}**: {count} trades\n"
            
            embed.add_field(name="Trade Leaderboard", value=leaderboard_text, inline=False)
        else:
            embed.add_field(name="Trade Leaderboard", value="No trade data yet", inline=False)
    
    elif category == "battles":
        # Battle Champions Leaderboard
        # First check if user_stats exists and has data
        if not hasattr(bot, 'user_stats') or not user_stats:
            embed = discord.Embed(
                title="⚔️ Battle Champions",
                description="No battle data has been recorded yet!",
                color=discord.Color.red()
            )
            return embed
        
        # Filter authorized users from stats
        filtered_stats = {user_id: stats for user_id, stats in user_stats.items() 
                         if user_id not in authorized_user_ids}
        
        # Calculate win rates and total battles
        battle_stats = []
        for user_id, stats in filtered_stats.items():
            battles = stats.get('battles_fought', 0)
            wins = stats.get('battles_won', 0)
            win_rate = (wins / battles) * 100 if battles > 0 else 0
            
            # Only include users who have fought at least 3 battles
            if battles >= 3:
                battle_stats.append((user_id, wins, battles, round(win_rate, 1)))
        
        # Sort by wins, then by win rate
        top_battlers = sorted(battle_stats, key=lambda x: (x[1], x[3]), reverse=True)[:10]
        
        embed = discord.Embed(
            title="⚔️ Battle Champions",
            description="Players ranked by battle victories",
            color=discord.Color.red()
        )
        
        if top_battlers:
            leaderboard_text = ""
            for idx, (user_id, wins, battles, win_rate) in enumerate(top_battlers):
                # Add medal emoji for top 3
                if idx == 0:
                    prefix = "🥇"
                elif idx == 1:
                    prefix = "🥈"
                elif idx == 2:
                    prefix = "🥉"
                else:
                    prefix = f"{idx+1}."
                
                leaderboard_text += f"{prefix} <@{user_id}>: **{wins}** wins ({battles} battles, {win_rate}% win rate)\n"

        embed = discord.Embed(
            title="📊 Leaderboard Help",
            description="View different types of leaderboards and statistics",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="Available Leaderboard Types",
            value=(
                "• `/leaderboard general` - General statistics (default)\n"
                "• `/leaderboard total` - Total cards leaderboard\n"
                "• `/leaderboard unique` - Unique cards leaderboard\n"
                "• `/leaderboard rarest` - Rarest cards and their owners\n"
                "• `/leaderboard activity` - Most active players\n"
                "• `/leaderboard traded` - Most frequently traded cards\n"
                "• `/leaderboard battles` - Battle champions\n"
                "• `/leaderboard help` - Show this help message"
            ),
            inline=False
        )
    
    else:
        # Invalid category
        embed = discord.Embed(
            title="📊 Leaderboard",
            description=f"Unknown leaderboard type: `{category}`",
            color=discord.Color.red()
        )
        
        embed.add_field(
            name="Available Types", 
            value=(
                "Use `/leaderboard help` to see available options"
            ),
            inline=False
        )
    
    # Set footer with timestamp
    current_time = datetime.datetime.now().strftime("%d-%m-%Y %H:%M")
    embed.set_footer(text=f"Stats as of {current_time}")
    return embed

#=================================================================
# COMMANDS
#=================================================================
# Admin Commands
@bot.command(name="blacklist")
@commands.check(is_authorized)
async def blacklist_user(ctx, user_id: str):
    if not user_id.isdigit():
        await ctx.send("Invalid user ID. Please provide a valid integer.")
        return

    user_id_str = user_id
    if BlacklistManager.add_to_blacklist(user_id_str):
        await ctx.send(f"User with ID {user_id} has been blacklisted.")
    else:
        await ctx.send(f"User with ID {user_id} is already blacklisted.")

@bot.command(name="unblacklist")
@commands.check(is_authorized)
async def unblacklist_user(ctx, user_id: str):
    if not user_id.isdigit():
        await ctx.send("Invalid user ID. Please provide a valid integer.")
        return

    user_id_str = user_id
    if BlacklistManager.remove_from_blacklist(user_id_str):
        await ctx.send(f"User with ID {user_id} has been removed from the blacklist.")
    else:
        await ctx.send(f"User with ID {user_id} is not in the blacklist.")
        
@bot.command(name="show_blacklist")
@commands.check(is_authorized)
async def show_blacklist(ctx):
    blacklist = BlacklistManager.load_blacklist()
    if blacklist:
        await ctx.send(f"Blacklisted user IDs: {', '.join(blacklist)}")
    else:
        await ctx.send("No users are currently blacklisted.")

@bot.command(name='force_backup')
@commands.check(is_authorized)
async def force_backup(ctx):
    try:
        create_backup()
        await ctx.send("Backup created successfully.")
    except Exception as e:
        await ctx.send(f"Backup failed: {str(e)}")
        logging.error(f"Manual backup failed: {e}", exc_info=True)

@bot.command(name='set_spawn_mode', help="Set the spawn mode to 'both', 'test', or 'none'.")
@commands.check(is_authorized)
async def set_spawn_mode(ctx, mode: str):
    global spawn_mode, is_test_mode
    mode = mode.lower()
    if mode in ['both', 'test', 'none']:
        spawn_mode = mode
        is_test_mode = spawn_mode == 'test'
        await ctx.send(f"Spawn mode set to {spawn_mode}.")
        logging.info(f"Spawn mode changed to {spawn_mode} by {ctx.author}.")
    else:
        await ctx.send("Invalid mode. Please choose from 'both', 'test', or 'none'.")

@bot.command(name='spawn_card', help="Spawn a specific card.")
@commands.check(is_authorized)
async def spawn_card_command(ctx, *, args: str):
    args = args.strip().lower()
    
    # Check if 'test' is in the arguments
    use_test_channel = False
    channel_index = None
    
    # Parse arguments to check for test flag or channel index
    if args.endswith(' test'):
        use_test_channel = True
        card_name = args[:-5].strip()  # Remove ' test' from the end
    elif ' in ' in args and args.split(' in ')[1].isdigit():
        parts = args.split(' in ')
        card_name = parts[0].strip()
        try:
            channel_index = int(parts[1].strip())
            if channel_index < 0 or channel_index >= len(channel_ids):
                await ctx.send(f"Invalid channel index. Please use a number between 0 and {len(channel_ids)-1}.")
                return
        except ValueError:
            await ctx.send("Invalid channel index format. Use 'spawn_card [card_name] in [channel_index]'")
            return
    else:
        card_name = args
    
    # Validate card name
    if not all(c.isalnum() or c.isspace() or c in ["'", "-"] for c in card_name):
        await ctx.send("Invalid card name. Only alphanumeric characters, spaces, apostrophes, and hyphens are allowed.")
        return

    card = next((card for card in cards if card_name == card["name"].lower() or card_name in [alias.lower() for alias in card.get("aliases", [])]), None)
    if card:
        # Choose the channel based on the parameters
        if use_test_channel:
            channel = bot.get_channel(int(test_channel_id))
            channel_name = "test channel"
        elif channel_index is not None:
            channel = bot.get_channel(int(channel_ids[channel_index]))
            channel_name = f"channel #{channel_index}"
        else:
            # Default to the first main channel if not specified
            channel = bot.get_channel(int(channel_ids[0]))
            channel_name = "main channel"

        if channel:
            embed = discord.Embed(title=f"A wild card has appeared!", description="Click the button below to catch it!")
            embed.set_image(url=card['spawn_image_url'])
            await channel.send(embed=embed, view=CatchView(card['name']))
            await ctx.send(f"{card['name']} has been spawned in the {channel_name}.")
        else:
            await ctx.send(f"Channel not found for {channel_name}.")
    else:
        await ctx.send("Card not found.")

@bot.command(name='givecard')
@commands.check(is_authorized)
async def admin_give_card(ctx, card: str, receiving_user: discord.Member):
    receiver_id = str(receiving_user.id)
    card_lower = card.lower()

    receiver_cards = player_cards.setdefault(receiver_id, [])
    receiver_cards.append(card)

    save_player_cards()  # Save the updated player cards
    await ctx.send(f"{ctx.author.mention} has given `{card}` to {receiving_user.mention}.")
    logging.info(f"Admin: {ctx.author} gave {card} to {receiving_user}.")

@bot.command(name='removecard')
@commands.check(is_authorized)
async def remove_card(ctx, card: str, user: discord.Member):
    user_id = str(user.id)
    card_lower = card.lower()

    user_cards = player_cards.get(user_id, [])
    if card_lower in map(str.lower, user_cards):
        actual_card_name = next(c for c in user_cards if c.lower() == card_lower)
        user_cards.remove(actual_card_name)
        save_player_cards()  # Save the updated player cards
        await ctx.send(f"Removed `{actual_card_name}` from {user.mention}'s inventory.")
        logging.info(f"Admin: {ctx.author} removed {actual_card_name} from {user}.")
    else:
        await ctx.send(f"{user.mention} does not have the card `{card}`.")
        logging.info(f"Admin: {ctx.author} attempted to remove {card} from {user}, but {user} did not possess {card}.")

@bot.command(name='view_user', aliases=['user_info', 'view_progress'], help="Admin command to view detailed user information")
@commands.check(is_authorized)
async def view_user(ctx, user: discord.Member):
    """
    Comprehensive admin tool to view all information about a user including:
    - Collection progress
    - Battle statistics
    - Trading activity
    - User account details
    Usage: !view_user @username
    """
    
    target_user_id = str(user.id)
    total_cards_count = len(cards)
    user_cards = player_cards.get(target_user_id, [])
    
    # Create main embed with user info
    embed = discord.Embed(
        title=f"👤 User Information: {user.display_name}",
        description=f"Detailed information for user ID: {target_user_id}",
        color=discord.Color.blue()
    )
    
    # Add account details
    created_at = user.created_at.strftime("%d-%m-%Y")
    joined_at = user.joined_at.strftime("%d-%m-%Y") if user.joined_at else "Unknown"
    
    embed.add_field(
        name="Account Details",
        value=f"• Discord Name: {user.name}\n"
              f"• Display Name: {user.display_name}\n"
              f"• Account Created: {created_at}\n"
              f"• Server Joined: {joined_at}\n"
              f"• Bot Status: {'🚫 Blacklisted' if BlacklistManager.is_blacklisted(target_user_id) else '✅ In good standing'}",
        inline=False
    )
    
    # Add card collection stats
    if not user_cards:
        embed.add_field(
            name="Card Collection",
            value="This user hasn't collected any cards yet.",
            inline=False
        )
    else:
        # Count total unique cards (no duplicates)
        unique_cards = set(user_cards)
        # Get card duplicates info
        card_counts = Counter(user_cards)
        # Calculate duplicates
        total_duplicates = len(user_cards) - len(unique_cards)
        
        # Find rarest card owned by rarity value
        card_rarity = {card_info['name']: card_info['rarity'] for card_info in cards}
        try:
            rarest_card = min(set(user_cards), key=lambda card_name: card_rarity.get(card_name, float('inf')))
            rarest_card_value = f"{rarest_card} ({card_rarity.get(rarest_card, '?')}% rarity)"
            
            most_duplicated_card = card_counts.most_common(1)[0][0] if total_duplicates > 0 else "None"
            most_duplicated_value = f"{most_duplicated_card} ({card_counts[most_duplicated_card]}x)" if most_duplicated_card != "None" else "None"
        except (ValueError, KeyError):
            rarest_card_value = "Unable to determine"
            most_duplicated_value = "Unable to determine"
        
        # Count cards by rarity tiers
        common_cards = sum(1 for card in unique_cards if card_rarity.get(card, 100) >= 20)
        uncommon_cards = sum(1 for card in unique_cards if 10 <= card_rarity.get(card, 100) < 20)
        rare_cards = sum(1 for card in unique_cards if 5 <= card_rarity.get(card, 100) < 10)
        very_rare_cards = sum(1 for card in unique_cards if card_rarity.get(card, 100) < 5)
        
        collection_info = (
            f"• Progress: **{len(unique_cards)}/{total_cards_count}** unique cards ({len(unique_cards)/total_cards_count*100:.1f}%)\n"
            f"• Total Cards: **{len(user_cards)}** (including {total_duplicates} duplicates)\n"
            f"• Card Rarity: {common_cards} common, {uncommon_cards} uncommon, {rare_cards} rare, {very_rare_cards} very rare\n"
            f"• Rarest Owned: {rarest_card_value}\n"
            f"• Most Duplicated: {most_duplicated_value}"
        )
        
        embed.add_field(name="Card Collection", value=collection_info, inline=False)
    
    # Add battle statistics if available
    if target_user_id in user_stats:
        stats = user_stats[target_user_id]
        battles_fought = stats.get('battles_fought', 0)
        battles_won = stats.get('battles_won', 0)
        win_rate = (battles_won / battles_fought * 100) if battles_fought > 0 else 0
        
        battle_info = (
            f"• Battles Fought: **{battles_fought}**\n"
            f"• Battles Won: **{battles_won}**\n"
            f"• Win Rate: **{win_rate:.1f}%**\n"
            f"• Cards Caught: **{stats.get('cards_caught', 0)}**\n"
            f"• Trades Completed: **{stats.get('trades_completed', 0)}**"
        )
        
        embed.add_field(name="Battle Statistics", value=battle_info, inline=False)
    else:
        embed.add_field(name="Battle Statistics", value="No battle data recorded for this user.", inline=False)

    await ctx.send(embed=embed)

    if user_cards:
        missing_cards = [card_info['name'] for card_info in cards if card_info['name'] not in user_cards]
        view = ProgressView(user_cards, missing_cards, user, display_name_override=user.display_name)
        await ctx.send("📚 **Card Collection Details:**", embed=view.create_embed(), view=view)
    
    # Log the action
    logging.info(f"Admin {ctx.author} viewed detailed information for {user.display_name} (ID: {target_user_id})")

@bot.command(name='shutdown', help="Shut down the bot.")
@commands.check(is_authorized)
async def shutdown(ctx):
    await ctx.send("Shutting down the bot...")
    logging.info(f"Shutdown command issued by {ctx.author}.")
    save_player_cards()
    await shutdown_bot()

# Card Collection Commands
@bot.tree.command(name="progress", description="Show your card collection progress")
async def progress_slash(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    total_cards = len(cards)
    user_cards = player_cards.get(user_id, [])
    missing_cards = [card['name'] for card in cards if card['name'] not in user_cards]

    view = ProgressView(user_cards, missing_cards, interaction.user)
    view.message = await interaction.response.send_message(embed=view.create_embed(), view=view)

@bot.tree.command(name="show_random_card", description="Show a random card you own")
async def show_random_card_slash(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    user_cards = player_cards.get(user_id, [])
    if not user_cards:
        await interaction.response.send_message("You don't have any cards yet!")
        return
    card_name = random.choice(user_cards)
    card = next((c for c in cards if c['name'] == card_name), None)
    if not card:
        await interaction.response.send_message(f"Card data for `{card_name}` not found.")
        return
    embed = discord.Embed(title=f"Random Card: {card['name']}")
    embed.set_image(url=card['card_image_url'])
    embed.add_field(name="Health", value=card["health"])
    embed.add_field(name="Attack", value=card["attack"])
    embed.add_field(name="Rarity", value=f"{card['rarity']}%")
    if "description" in card:
        embed.add_field(name="Description", value=card["description"], inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="see_card", description="View details of a card you own")
@app_commands.describe(card_name="Name of the card you want to see")
@app_commands.autocomplete(card_name=card_name_autocomplete)
async def see_card_slash(interaction: discord.Interaction, card_name: str):
    user_id = str(interaction.user.id)
    user_cards = player_cards.get(user_id, [])
    if not user_cards:
        await interaction.response.send_message("You haven't caught any cards yet.", ephemeral=True)
        return

    card_name_lower = card_name.strip().lower()
    user_card = next(
        (card for card in user_cards if
         card.lower() == card_name_lower or
         any(card_name_lower == alias.lower() for alias in next((c.get('aliases', []) for c in cards if c['name'].lower() == card.lower()), []))
        ),
        None
    )
    if user_card:
        selected_card = next(
            card for card in cards
            if card["name"].lower() == card_name_lower or
               card_name_lower in [alias.lower() for alias in card.get("aliases", [])]
        )
        embed = discord.Embed(title=f"Here's your {selected_card['name']}", description="")
        embed.set_image(url=selected_card["card_image_url"])
        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message("You don't have this card.", ephemeral=True)

@bot.tree.command(name="stats", description="Show stats for a specific card")
@app_commands.describe(card_name="Name of the card to show stats for")
@app_commands.autocomplete(card_name=card_name_autocomplete)
async def stats_slash(interaction: discord.Interaction, card_name: str):
    user_id = str(interaction.user.id)
    user_cards = player_cards.get(user_id, [])
    card_name_lower = card_name.strip().lower()
    # Only search in user's cards
    user_card = next(
        (card for card in user_cards if
         card.lower() == card_name_lower or
         any(card_name_lower == alias.lower() for alias in next((c.get('aliases', []) for c in cards if c['name'].lower() == card.lower()), []))
        ),
        None
    )
    if user_card:
        selected_card = next(
            card for card in cards
            if card["name"].lower() == card_name_lower or
               card_name_lower in [alias.lower() for alias in card.get("aliases", [])]
        )
        embed = discord.Embed(title=f"Stats for {selected_card['name']}", description="")
        embed.add_field(name="Health", value=selected_card["health"], inline=True)
        embed.add_field(name="Damage", value=selected_card["attack"], inline=True)
        embed.add_field(name="Rarity", value=f"{selected_card['rarity']}%", inline=True)
        embed.add_field(name="Description", value=selected_card["description"], inline=False)
        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message("You don't have this card.", ephemeral=True)

@bot.tree.command(name="give", description="Give a card you own to another user")
@app_commands.describe(
    receiving_user="The user you want to give a card to",
    card="The card you want to give"
)
@app_commands.autocomplete(card=card_name_autocomplete)
async def give_card_slash(
    interaction: discord.Interaction, 
    receiving_user: discord.Member,
    card: str
):
    sender_id = str(interaction.user.id)
    receiver_id = str(receiving_user.id)
    card_lower = card.lower()
    
    if receiving_user.id == interaction.user.id:
        await interaction.response.send_message("You can't give a card to yourself!", ephemeral=True)
        return
    if receiving_user.bot:
        await interaction.response.send_message("You can't give a card to a bot!", ephemeral=True)
        return

    async with battle_lock:
        try:
            sender_cards = player_cards.get(sender_id, [])
            if not any(
                card_lower == c.lower() or 
                card_lower in [alias.lower() for alias in next((card_obj['aliases'] for card_obj in cards if card_obj['name'].lower() == c.lower()), [])]
                for c in sender_cards
            ):
                await interaction.response.send_message(f"You don't own the card `{card}`.", ephemeral=True)
                return
            
            # Find the exact card name (preserving case)
            actual_card_name = next(
                (c for c in sender_cards if
                 card_lower == c.lower() or
                 card_lower in [alias.lower() for alias in next((card_obj['aliases'] for card_obj in cards if card_obj['name'].lower() == c.lower()), [])]
                ),
                None
            )
            if not actual_card_name:
                await interaction.response.send_message(f"Error finding card `{card}` in your inventory.", ephemeral=True)
                return
                
            # Remove the card from the sender's inventory
            sender_cards.remove(actual_card_name)
            receiver_cards = player_cards.setdefault(receiver_id, [])
            receiver_cards.append(actual_card_name)
            save_player_cards()
            await interaction.response.send_message(
                f"{interaction.user.mention} has given `{actual_card_name}` to {receiving_user.mention}."
            )
            logging.info(f"{interaction.user} gave {actual_card_name} to {receiving_user}.")
        except Exception as e:
            logging.error(f"Error in card transfer: {e}", exc_info=True)
            await interaction.response.send_message("An error occurred during card transfer.", ephemeral=True)

@bot.tree.command(name="battle", description="Challenge another user to a card battle")
@app_commands.describe(
    opponent="The user you want to battle",
    help="Show battle help before starting"
)
async def battle_slash(
    interaction: discord.Interaction,
    opponent: discord.Member,
    help: bool = False
):
    challenger = interaction.user
    if opponent.id == challenger.id:
        await interaction.response.send_message("You can't battle yourself!", ephemeral=True)
        return
    if opponent.bot:
        await interaction.response.send_message("You can't battle a bot!", ephemeral=True)
        return

    challenger_id = str(challenger.id)
    opponent_id = str(opponent.id)

    # Check if both players have cards
    if challenger_id not in player_cards or not player_cards[challenger_id]:
        await interaction.response.send_message("You don't have any cards to battle with!", ephemeral=True)
        return
    if opponent_id not in player_cards or not player_cards[opponent_id]:
        await interaction.response.send_message(f"{opponent.display_name} doesn't have any cards to battle with!", ephemeral=True)
        return

    # Check for ongoing battles
    if not hasattr(bot, 'ongoing_battles'):
        bot.ongoing_battles = set()
    if not hasattr(bot, 'active_battles'):
        bot.active_battles = []

    if challenger_id in bot.ongoing_battles:
        await interaction.response.send_message("You're already in a battle!", ephemeral=True)
        return
    if opponent_id in bot.ongoing_battles:
        await interaction.response.send_message(f"{opponent.display_name} is already in a battle!", ephemeral=True)
        return

    # Show help if requested
    if help:
        embed = discord.Embed(
            title="Card Battle Help",
            description="How to battle with your cards",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="Starting a Battle",
            value="Use `/battle @user` to challenge another player",
            inline=False
        )
        embed.add_field(
            name="Selecting Cards",
            value="After the opponent accepts, both players select cards using dropdowns/buttons. You can select up to 3 cards.",
            inline=False
        )
        embed.add_field(
            name="Confirming Selection",
            value="Click the 'Submit Selection' button when you're ready.",
            inline=False
        )
        embed.add_field(
            name="Battle Process",
            value="Cards will automatically take turns attacking until one side has no cards left.",
            inline=False
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        # Continue to start the battle after showing help
        followup = interaction.followup
    else:
        await interaction.response.defer()
        followup = interaction.followup

    # Add both players to ongoing battles
    bot.ongoing_battles.add(challenger_id)
    bot.ongoing_battles.add(opponent_id)

    # Start the battle UI flow
    try:
        # Use the interaction as the context for CardBattle
        battle = CardBattle(interaction, challenger, opponent)
        bot.active_battles.append(battle)
        await battle.start_battle()
    except Exception as e:
        logging.error(f"Battle error: {e}", exc_info=True)
        await followup.send("An error occurred while setting up the battle.", ephemeral=True)
        bot.ongoing_battles.discard(challenger_id)
        bot.ongoing_battles.discard(opponent_id)
        if 'battle' in locals() and battle in getattr(bot, 'active_battles', []):
            bot.active_battles.remove(battle)

class Trade(commands.GroupCog, name="trade"):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="start", description="Start a trade with another user")
    @app_commands.describe(user="The user you want to trade with")
    async def start(self, interaction: discord.Interaction, user: discord.Member):
        initiator_id = str(interaction.user.id)
        recipient_id = str(user.id)
        if initiator_id == recipient_id:
            await interaction.response.send_message("You can't trade with yourself!", ephemeral=True)
            return
        if user.bot:
            await interaction.response.send_message("You can't trade with a bot!", ephemeral=True)
            return
        if initiator_id not in player_cards or not player_cards[initiator_id]:
            await interaction.response.send_message("You don't have any cards to trade!", ephemeral=True)
            return
        if recipient_id not in player_cards or not player_cards[recipient_id]:
            await interaction.response.send_message(f"{user.display_name} doesn't have any cards to trade!", ephemeral=True)
            return
        if not hasattr(self.bot, 'active_trades'):
            self.bot.active_trades = {}
        if initiator_id in self.bot.active_trades:
            await interaction.response.send_message("You're already in an active trade!", ephemeral=True)
            return
        if recipient_id in self.bot.active_trades:
            await interaction.response.send_message(f"{user.display_name} is already in an active trade!", ephemeral=True)
            return
        trade_session = TradeSession(interaction, interaction.user, user)
        self.bot.active_trades[initiator_id] = trade_session
        self.bot.active_trades[recipient_id] = trade_session
        await trade_session.start_trade()
        await interaction.response.send_message(f"Trade started with {user.mention}!", ephemeral=True)

    @app_commands.command(name="add", description="Add a card to your trade offer")
    @app_commands.describe(card="The card you want to add")
    async def add(self, interaction: discord.Interaction, card: str):
        user_id = str(interaction.user.id)
        if not hasattr(self.bot, 'active_trades') or user_id not in self.bot.active_trades:
            await interaction.response.send_message("You're not in an active trade!", ephemeral=True)
            return
        trade = self.bot.active_trades[user_id]
        trade.reset_activity_timer()
        if not trade.active:
            del self.bot.active_trades[user_id]
            await interaction.response.send_message("That trade is no longer active.", ephemeral=True)
            return
        is_initiator = (user_id == trade.initiator_id)
        if (is_initiator and trade.initiator_confirmed) or (not is_initiator and trade.recipient_confirmed):
            await interaction.response.send_message("You've already confirmed the trade! Use `/trade unconfirm` to make changes.", ephemeral=True)
            return
        user_cards = player_cards.get(user_id, [])
        card_lower = card.lower()
        found_card = None
        for c in user_cards:
            card_data = next((ci for ci in cards if ci['name'].lower() == c.lower()), None)
            if c.lower() == card_lower:
                found_card = c
                break
            elif card_data and 'aliases' in card_data:
                if card_lower in [alias.lower() for alias in card_data['aliases']]:
                    found_card = c
                    break
        if not found_card:
            await interaction.response.send_message(f"You don't have a card named `{card}`!", ephemeral=True)
            return
        if is_initiator:
            if found_card in trade.initiator_cards:
                await interaction.response.send_message(f"You've already added `{found_card}` to the trade!", ephemeral=True)
                return
            trade.initiator_cards.append(found_card)
        else:
            if found_card in trade.recipient_cards:
                await interaction.response.send_message(f"You've already added `{found_card}` to the trade!", ephemeral=True)
                return
            trade.recipient_cards.append(found_card)
        await interaction.response.send_message(f"Added `{found_card}` to your trade offer.", ephemeral=True)
        await trade.update_trade_status()

    @app_commands.command(name="remove", description="Remove a card from your trade offer")
    @app_commands.describe(card="The card you want to remove")
    async def remove(self, interaction: discord.Interaction, card: str):
        user_id = str(interaction.user.id)
        if not hasattr(self.bot, 'active_trades') or user_id not in self.bot.active_trades:
            await interaction.response.send_message("You're not in an active trade!", ephemeral=True)
            return
        trade = self.bot.active_trades[user_id]
        trade.reset_activity_timer()
        if not trade.active:
            del self.bot.active_trades[user_id]
            await interaction.response.send_message("That trade is no longer active.", ephemeral=True)
            return
        is_initiator = (user_id == trade.initiator_id)
        if (is_initiator and trade.initiator_confirmed) or (not is_initiator and trade.recipient_confirmed):
            await interaction.response.send_message("You've already confirmed the trade! Use `/trade unconfirm` to make changes.", ephemeral=True)
            return
        card_lower = card.lower()
        user_trade_cards = trade.initiator_cards if is_initiator else trade.recipient_cards
        card_to_remove = None
        for c in user_trade_cards:
            card_data = next((ci for ci in cards if ci['name'].lower() == c.lower()), None)
            if c.lower() == card_lower:
                card_to_remove = c
                break
            elif card_data and 'aliases' in card_data:
                if card_lower in [alias.lower() for alias in card_data['aliases']]:
                    card_to_remove = c
                    break
        if not card_to_remove:
            await interaction.response.send_message(f"You don't have `{card}` in your trade offer!", ephemeral=True)
            return
        user_trade_cards.remove(card_to_remove)
        await interaction.response.send_message(f"Removed `{card_to_remove}` from your trade offer.", ephemeral=True)
        await trade.update_trade_status()

    @app_commands.command(name="confirm", description="Confirm your trade offer")
    async def confirm(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        if not hasattr(self.bot, 'active_trades') or user_id not in self.bot.active_trades:
            await interaction.response.send_message("You're not in an active trade!", ephemeral=True)
            return
        trade = self.bot.active_trades[user_id]
        trade.reset_activity_timer()
        if not trade.active:
            del self.bot.active_trades[user_id]
            await interaction.response.send_message("That trade is no longer active.", ephemeral=True)
            return
        is_initiator = (user_id == trade.initiator_id)
        if is_initiator:
            trade.initiator_confirmed = True
        else:
            trade.recipient_confirmed = True
        await interaction.response.send_message("Trade confirmed!", ephemeral=True)
        await trade.update_trade_status()
        if trade.initiator_confirmed and trade.recipient_confirmed:
            await trade.finalize_trade()
            self.bot.active_trades.pop(trade.initiator_id, None)
            self.bot.active_trades.pop(trade.recipient_id, None)

    @app_commands.command(name="unconfirm", description="Unconfirm your trade offer")
    async def unconfirm(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        if not hasattr(self.bot, 'active_trades') or user_id not in self.bot.active_trades:
            await interaction.response.send_message("You're not in an active trade!", ephemeral=True)
            return
        trade = self.bot.active_trades[user_id]
        trade.reset_activity_timer()
        if not trade.active:
            del self.bot.active_trades[user_id]
            await interaction.response.send_message("That trade is no longer active.", ephemeral=True)
            return
        is_initiator = (user_id == trade.initiator_id)
        if (is_initiator and not trade.initiator_confirmed) or (not is_initiator and not trade.recipient_confirmed):
            await interaction.response.send_message("You haven't confirmed the trade yet!", ephemeral=True)
            return
        if is_initiator:
            trade.initiator_confirmed = False
        else:
            trade.recipient_confirmed = False
        await interaction.response.send_message("Trade unconfirmed.", ephemeral=True)
        await trade.update_trade_status()

    @app_commands.command(name="cancel", description="Cancel the trade")
    async def cancel(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        if not hasattr(self.bot, 'active_trades') or user_id not in self.bot.active_trades:
            await interaction.response.send_message("You're not in an active trade!", ephemeral=True)
            return
        trade = self.bot.active_trades[user_id]
        if not trade.active:
            del self.bot.active_trades[user_id]
            await interaction.response.send_message("That trade is no longer active.", ephemeral=True)
            return
        await trade.cancel_trade(f"Trade cancelled by {interaction.user.mention}")
        self.bot.active_trades.pop(trade.initiator_id, None)
        self.bot.active_trades.pop(trade.recipient_id, None)
        await interaction.response.send_message("Trade cancelled.", ephemeral=True)

    @app_commands.command(name="status", description="Show the status of your current trade")
    async def status(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        if not hasattr(self.bot, 'active_trades') or user_id not in self.bot.active_trades:
            await interaction.response.send_message("You're not in an active trade!", ephemeral=True)
            return
        trade = self.bot.active_trades[user_id]
        trade.reset_activity_timer()
        if not trade.active:
            del self.bot.active_trades[user_id]
            await interaction.response.send_message("That trade is no longer active.", ephemeral=True)
            return
        await trade.update_trade_status()
        await interaction.response.send_message("Trade status updated.", ephemeral=True)

    @app_commands.command(name="help", description="Show help for trading")
    async def help(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="Card Trading Help",
            description="How to trade cards with other players",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="Starting a Trade",
            value="Use `/trade start @user` to start trading with another player",
            inline=False
        )
        embed.add_field(
            name="Adding Cards",
            value="Use `/trade add [card name]` to add a card to your trade offer",
            inline=False
        )
        embed.add_field(
            name="Removing Cards",
            value="Use `/trade remove [card name]` to remove a card from your offer",
            inline=False
        )
        embed.add_field(
            name="Confirming Trade", 
            value="Use `/trade confirm` when you're happy with the deal\n"
                  "Both players must confirm for the trade to complete",
            inline=False
        )
        embed.add_field(
            name="Other Commands",
            value="• `/trade unconfirm` - Remove your confirmation\n"
                  "• `/trade cancel` - Cancel the trade entirely\n"
                  "• `/trade status` - Check the current status of your trade",
            inline=False
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

# Misc Commands
@bot.tree.command(name="hello", description="Get a greeting from the bot")
async def hello_slash(interaction: discord.Interaction):
    await interaction.response.send_message('Hello! I am the 235th dex!')

@bot.tree.command(name="random_number", description="Generate a random number")
async def random_number_slash(interaction: discord.Interaction):
    random_number = random.randint(0, 10000000)
    await interaction.response.send_message(f'Your random number is: {random_number}')

@bot.tree.command(name="commands_dex", description="Show all available commands for the 235th Dex")
async def commands_slash(interaction: discord.Interaction):
    
    embed = discord.Embed(
        title="🎮 235th Dex Command Center",
        description="Here are all the commands available to you:",
        color=discord.Color.purple()
    )
    
    # General Commands
    embed.add_field(
        name="📝 General",
        value=(
            "`/hello` - Get a greeting from the bot\n"
            "`/random_number` - Generate a random number\n"
            "`/info_dex` - View information about the bot\n"
            "`/commands_dex` - Show this command list\n"
            "`/gud_boy` - Shows a good boy GIF"
        ),
        inline=False
    )
    
    # Card Collection Commands
    embed.add_field(
        name="🃏 Card Collection",
        value=(
            "`/see_card [card name]` - View a card you've caught\n"
            "`/show_random_card` - View a random card you've caught\n"
            "`/progress` - Show your card collection progress\n"
            "`/stats [card name]` - Show stats for a specific card\n"
            "`/give @user [card name]` - Give a card to another user"
        ),
        inline=False
    )
    
    # Battle Commands
    embed.add_field(
        name="⚔️ Battle System",
        value=(
            "`/battle @user` - Challenge another user to a battle\n"
            "`/battle add [card name]` - Add a card to your battle team\n"
            "`/battle cards` - See your currently selected cards\n"
            "`/battle ready` - Confirm your card selection\n"
            "`/battle help` - Get help with the battle system"
        ),
        inline=False
    )

    embed.add_field(
        name="🔄 Trading System",
        value=(
            "`/trade @user` - Start a card trade with another user\n"
            "`/trade add [card name]` - Add a card to your trade offer\n"
            "`/trade remove [card name]` - Remove a card from your offer\n"
            "`/trade confirm` - Confirm the trade deal\n"
            "`/trade unconfirm` - Unconfirm the trade deal\n"
            "`/trade status` - Check your current trade\n"
            "`/trade help` - Get help with trading"
        ),
        inline=False
    )
    
    # Bot Stats
    embed.add_field(
        name="📊 Leaderboard",
        value="`/leaderboard [Optional mode]` - Show general statistics about the card game",
        inline=False
    )
    
    embed.set_thumbnail(url="https://cdn.discordapp.com/app-icons/1321813254128930867/450fa2947cf99f3182797b7b503c5c63.png")

    embed.set_footer(text="Need help? Join our support server: discord.gg/VMhy3VSXYx")
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="info_dex", description="View information about the bot")
async def info_slash(interaction: discord.Interaction):
    total_lines_of_code = count_lines_of_code()
    uptime = datetime.datetime.now() - start_time
    days, remainder = divmod(int(uptime.total_seconds()), 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)
    uptime_str = f"{days}d {hours}h {minutes}m"

    total_users = len(player_cards)
    total_cards_collected = sum(len(cards) for cards in player_cards.values())
    backup_count = len([f for f in os.listdir(backup_folder) if f.startswith("player_cards_backup_")])

    embed = discord.Embed(
        title="235th Dex Information",
        description="Technical details and status information",
        color=discord.Color.teal()
    )

    embed.add_field(
        name="Version",
        value="2.0.0 - \"The Slash Command Update\"", 
        inline=False
    )
    embed.add_field(
        name="Developers",
        value=(
            "**Current:** <@573878397952851988>\n"
            "**Retired:** <@1035607651985403965>, <@845973389415284746>"
        ),
        inline=True
    )
    embed.add_field(
        name="System Stats",
        value=(
            f"• **Users:** {total_users}\n"
            f"• **Cards Collected:** {total_cards_collected}\n"
            f"• **Uptime:** {uptime_str}\n"
            f"• **Lines of Code:** {total_lines_of_code}"
        ),
        inline=False
    )
    embed.add_field(
        name="Database",
        value=f"• **Status:** Healthy\n• **Backups:** {backup_count}/{MAX_BACKUPS}",
        inline=True
    )
    embed.add_field(
        name="Latest Changes",
        value=(
            "• All commands are now slash commands\n"
            "• Added new cards\n"
            "• Bugfixes and improvements"
        ),
        inline=False
    )
    embed.set_footer(text=f"Last restarted: {datetime.datetime.now().strftime('%d-%m-%Y %H:%M')}")

    await interaction.response.send_message(embed=embed)

@bot.command(name='celebrate', help="Posts a celebration animation (admin only)")
@commands.check(is_authorized)
async def play_gif(ctx):
    embed = discord.Embed(title="Celebration Time!")
    embed.set_image(url="https://cdn.discordapp.com/attachments/1322197080625647627/1348320094660464863/image0.gif?ex=67cf0871&is=67cdb6f1&hm=d47b2a88b5fe88a4da2c03c78a94f67eb66b9efa0104c69b72c6a9006c4c95e2")
    await ctx.send(embed=embed)

@bot.tree.command(name="gud_boy", description="Shows a good boy GIF")
async def gud_boy_slash(interaction: discord.Interaction):
    embed = discord.Embed(title="Good boy!")
    embed.set_image(url="https://cdn.discordapp.com/attachments/1258772746897461458/1340729833889464422/image0.gif?ex=67c92c35&is=67c7dab5&hm=0b58bb55cc24fbeb9e74f77ed4eedaf4d48ba68f61e82922b9632c6a61f7713b&")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="leaderboard", description="Show various leaderboards and statistics")
async def leaderboard_slash(interaction: discord.Interaction):
    embed = await get_leaderboard_embed("general")
    view = LeaderboardView(interaction, initial_category="general")
    await interaction.response.send_message(embed=embed, view=view)

#=================================================================
# EVENT HANDLERS
#=================================================================
@bot.event
async def on_ready():
    # Do some commands stuff
    global spawned_messages
    load_player_cards()  # Load player cards when the bot starts
    validate_card_data()
    await bot.tree.sync()
    await bot.add_cog(Trade(bot))
    print(f'We have logged in as {bot.user}')
    logging.info("Logging is configured correctly.")
    
    # Send online message to all channels
    all_channels = [bot.get_channel(int(test_channel_id))] + [bot.get_channel(int(id)) for id in channel_ids]
    logging.info(f"Attempting to send online message to {len(all_channels)} channels")
    
    for channel in all_channels:
        if channel:
            try:
                await channel.send("235th dex is online! Type /commands_dex to see the available commands.")
                logging.info(f"Sent online message to channel {channel.id}")
            except Exception as e:
                logging.error(f"Failed to send message to channel {channel.id}: {e}")
        else:
            logging.error(f"Channel not found.")
    
    # Disable buttons of previous cards on restart
    try:
        for message in spawned_messages:
            if hasattr(message, 'components') and message.components:
                view = message.components[0]
                for item in view.children:
                    if isinstance(item, Button):
                        item.disabled = True
                await message.edit(view=view)
    except Exception as e:
        logging.error(f"Failed to disable buttons on previous cards: {e}")

    spawned_messages = []

    spawn_card.start()
    backup_player_data.start()  # Start the backup task

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        await ctx.send(f"Command not found. Use `/commands_dex` to see available commands.")
    elif isinstance(error, commands.MissingRequiredArgument):
        param = error.param.name
        await ctx.send(f"Missing required argument: `{param}`. Check command usage with `/commands_dex`.")
    elif isinstance(error, commands.BadArgument):
        if "Member" in str(error):
            await ctx.send("Could not find that user. Please @mention a valid user.")
        else:
            await ctx.send(f"Invalid argument provided. {str(error)}")
    elif isinstance(error, commands.UserInputError):
        await ctx.send(str(error))
    elif isinstance(error, commands.DisabledCommand):
        await ctx.send("This command is currently disabled.")
    elif isinstance(error, commands.CommandInvokeError):
        original = error.original
        if isinstance(original, discord.Forbidden):
            await ctx.send("I don't have permission to do that.")
        elif isinstance(original, discord.HTTPException):
            await ctx.send("There was a network error. Please try again later.")
        else:
            logging.error(f"Command {ctx.command} raised an error: {original}", exc_info=original)
            await ctx.send(f"An error occurred while running the command: {type(original).__name__}")
    elif isinstance(error, commands.TooManyArguments):
        await ctx.send("Too many arguments provided. Check command usage with `/commands_dex`.")
    elif isinstance(error, commands.CheckFailure):
        if not any(msg in str(error) for msg in ["blacklisted", "test mode"]):
            await ctx.send("You do not have permission to use this command.")
    else:
        logging.error(f"Unhandled error: {error}", exc_info=error)
        await ctx.send("An unexpected error occurred. The developers have been notified.")

@bot.event
async def on_guild_join(guild):
    if guild.id not in allowed_guilds:
        logging.warning(f"Unauthorized guild joined: {guild.name} (ID: {guild.id}). Leaving the server.")
        if guild.system_channel:
            await guild.system_channel.send("This bot is restricted to specific servers. Leaving now.")
        await guild.leave()
    else:
        logging.info(f"Joined authorized guild: {guild.name} (ID: {guild.id}).")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    content = message.content.lower()

    responses = {
        "good bot": {
            "title": "good human!",
            "image": "https://media.discordapp.net/attachments/1258772746897461458/1340729833889464422/image0.gif?ex=67c92c35&is=67c7dab5&hm=0b58bb55cc24fbeb9e74f77ed4eedaf4d48ba68f61e82922b9632c6a61f7713b&="
        },
        "bad bot": {
            "title": "I think you meant to say... good bot",
            "image": "https://media.discordapp.net/attachments/1322202354421989414/1346845659252391999/th-2404264802.jpg?ex=67c9ab44&is=67c859c4&hm=bc40b032057c8635bedfcc07519d561bc58edad1d2e1715a24694e5f43112108&=&format=webp"	
        }
    }

    for trigger, response in responses.items():
        if trigger in content:
            embed = discord.Embed(title=response["title"])
            embed.set_image(url=response["image"])
            await message.channel.send(embed=embed)
            break
    
    if content.startswith('!'):
        user_id = str(message.author.id)
        is_auth = user_id in authorized_user_ids
    
        if content.strip() == '!commands_dex':
            await message.channel.send("Please use `/commands_dex` instead.")
            return
        elif content.startswith('!!'):
            return
        elif not is_auth:
            await message.channel.send("❗ Old '!' commands are being phased out. Please use slash commands instead (type `/` to see available commands).")
            return
        else:
            # Allow authorized users to use all commands
            await bot.process_commands(message)
            return

    await bot.process_commands(message)

@bot.before_invoke
async def check_conditions(ctx):
    if BlacklistManager.is_blacklisted(str(ctx.author.id)) and str(ctx.author.id) not in authorized_user_ids:
        await ctx.send("You are blacklisted and cannot use this bot.")
        raise commands.CheckFailure("User is blacklisted.")
    
    if is_test_mode and str(ctx.author.id) not in authorized_user_ids and not ctx.command.name == 'set_spawn_mode':
        await ctx.send("We are currently updating the bot, please wait until we are finished.")
        raise commands.CheckFailure("Bot is in test mode.")

@tasks.loop(minutes=45)
async def spawn_card():
    global spawned_messages, last_spawned_card_per_channel
    channels = []
    try:
        # Disable buttons of previous cards
        for message in spawned_messages:
            try:
                view = View.from_message(message)
                for item in view.children:
                    if isinstance(item, Button):
                        item.disabled = True
                await message.edit(view=view)
            except discord.NotFound:
                logging.info(f"Message {message.id} not found, likely deleted")
            except discord.HTTPException as e:
                logging.error(f"HTTP error disabling buttons: {e}")
            except Exception as e:
                logging.error(f"Error disabling buttons on message {message.id}: {e}")
        
        spawned_messages = []

        # Get valid channels based on spawn mode
        channels = get_spawn_channels()
        if not channels:
            logging.info("No channels configured for spawning cards.")
            return

        spawn_titles = [
            "A wild card has appeared!", "Think fast, chucklenuts!",
            "Look at this beauty, what might it be?", "Houston, we have a card!",
            "Card alert!", "Card incoming!", "Be fast!", "Catch it if you can!",
            "Card on the loose!", "Card on 12'oclock!"
        ]
        
        for channel in channels:
            try:
                last_card_name = last_spawned_card_per_channel.get(channel.id)
                card = select_random_card(exclude_card_name=last_card_name)
                last_spawned_card_per_channel[channel.id] = card['name']

                spawn_title = random.choice(spawn_titles)
                embed = discord.Embed(title=spawn_title, description="Click the button below to catch it!")
                embed.set_image(url=card['spawn_image_url'])

                msg = await channel.send(embed=embed, view=CatchView(card['name']),
                                        allowed_mentions=discord.AllowedMentions.none())
                spawned_messages.append(msg)
                logging.info(f"Card spawned in channel {channel.id}: {card['name']}")
            except discord.Forbidden:
                logging.error(f"Missing permissions to send messages in channel {channel.id}")
            except discord.HTTPException as e:
                logging.error(f"Failed to send card to channel {channel.id}: {e}")
            except Exception as e:
                logging.error(f"Unexpected error sending card to channel {channel.id}: {e}")

    except Exception as e:
        logging.error(f"An error occurred during card spawn: {e}", exc_info=True)
        for channel in channels:
            try:
                await channel.send("An error occurred while spawning cards.")
            except:
                pass

#=================================================================
# INITIALISATION & STARTUP
#=================================================================
# Handle shutdown signal
def handle_shutdown_signal(signal, frame):
    save_player_cards()  # Save player cards on shutdown
    loop = asyncio.get_event_loop()
    loop.create_task(shutdown_bot())

signal.signal(signal.SIGINT, handle_shutdown_signal)
signal.signal(signal.SIGTERM, handle_shutdown_signal)

# Custom shutdown function
async def shutdown_bot():
    global spawned_messages
    for message in spawned_messages:
        try:
            view = View.from_message(message)
            for item in view.children:
                if isinstance(item, Button):
                    item.disabled = True
            await message.edit(view=view)
        except Exception as e:
            logging.error(f"Failed to disable button on shutdown for message {getattr(message, 'id', '?')}: {e}")

    all_channels = [bot.get_channel(int(test_channel_id))] + [bot.get_channel(int(id)) for id in channel_ids]
    logging.info(f"Attempting to send disconnect message to {len(all_channels)} channels")
    
    for channel in all_channels:
        if channel:
            try:
                if channel.id == int(test_channel_id):
                    if spawn_mode == 'both':
                        await channel.send(f"<@573878397952851988>, Main bot going offline, please renew server if needed.")
                    else:
                        await channel.send("235th dex going offline")
                else:
                    await channel.send("235th dex going offline")
                logging.info(f"Sent disconnect message to channel {channel.id}")
            except Exception as e:
                logging.error(f"Failed to send message to channel {channel.id}: {e}")
        else:
            logging.error(f"Channel not found.")
    
    logging.info("235th dex going offline")
    create_backup()
    await bot.close()

if __name__ == "__main__":
    retry_count = 0
    max_retries = 5

    while retry_count < max_retries:
        try:
            bot.run(token)
            break
        except discord.errors.ConnectionClosed as e:
            retry_count += 1
            logging.warning(f"Connection closed. Attempting reconnect {retry_count}/{max_retries}")
            time.sleep(5)  # Wait before retrying
        except client_exceptions.ClientConnectorError as e:
            retry_count += 1
            logging.warning(f"Connection error: {e}. Attempting reconnect {retry_count}/{max_retries}")
            time.sleep(10)  # Longer wait for DNS issues
        except Exception as e:
            logging.error(f"Unhandled error: {e}")
            break
    
    if retry_count >= max_retries:
        logging.critical(f"Failed to connect after {max_retries} attempts. Giving up.")
        # Save data before exiting to prevent data loss
        save_player_cards()
        create_backup()
        print(f"Bot shutdown after {max_retries} failed connection attempts. Check logs for details.")
        exit(1)