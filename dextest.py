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

from typing import Dict, List, Optional, Set, Tuple
from collections import Counter
from aiohttp import client_exceptions

import discord # type: ignore
from discord import Interaction
from discord.ext import commands, tasks # type: ignore
from discord.ui import Button, View, Modal, TextInput, Select #type:ignore 
from dotenv import load_dotenv # type: ignore //please ensure that you have python-dotenv installed (command is "pip install python-dotenv")

# Import the cards list from cards.py
from cards import cards

# Configuring logging into the terminal
logging.basicConfig(level=logging.INFO, format='%(asctime)s:%(levelname)s:%(name)s: %(message)s')

# Loading the token from the .env file
load_dotenv()
token = os.getenv('DISCORD_TOKEN')
channel_id = os.getenv('CHANNEL_ID')
test_channel_id = os.getenv('TEST_CHANNEL_ID')
spawn_mode = os.getenv('SPAWN_MODE', 'both').lower()

# Load authorized user IDS from .env
authorized_user_ids = os.getenv('AUTHORIZED_USER_IDS', '').split(',')
authorized_user_ids = [user_id.strip() for user_id in authorized_user_ids if user_id.strip().isdigit()]
logging.info(f"Authorized user IDs loaded.")

if not token: # If it can't find the token, error message and exit will occur
    logging.error("DISCORD_TOKEN missing!") 
    exit(1)

if not channel_id: # If it can't find the ID, error message and exit will occur
    logging.error("CHANNEL_ID missing!") 
    exit(1)

# Bot Configuration, this holds what character you have to use to give the bot a command (in this case "!")
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# 3 authorised user id's, this checks for them
def is_authorized(ctx):
    return str(ctx.author.id) in authorized_user_ids

is_test_mode = spawn_mode == 'test'

# File to store blacklisted user IDs
blacklist_file = "blacklist.json"

# The modal lock collections
battle_lock = asyncio.Lock()
trade_lock = asyncio.Lock()
submit_lock = asyncio.Lock()

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

# Add a user to the blacklist
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

# Remove a user from the blacklist
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

@bot.before_invoke
async def check_conditions(ctx):
    if BlacklistManager.is_blacklisted(str(ctx.author.id)) and str(ctx.author.id) not in authorized_user_ids:
        await ctx.send("You are blacklisted and cannot use this bot.")
        raise commands.CheckFailure("User is blacklisted.")
    
    if is_test_mode and str(ctx.author.id) not in authorized_user_ids and not ctx.command.name == 'set_spawn_mode':
        await ctx.send("We are currently updating the bot, please wait until we are finished.")
        raise commands.CheckFailure("Bot is in test mode.")

def validate_recipient(ctx, recipient):
    if not recipient:
        raise commands.UserInputError("Please specify a user. Usage: `!{ctx.command.name} @user`")
    
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

# Player cards view starter
player_cards = {}

# Load player cards from a JSON file
def load_player_cards() -> None:
    global player_cards
    try:
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
        # Try to recover from the most recent backup
        recover_from_backup()
    except PermissionError:
        logging.error("Permission denied when trying to access player cards file")
        player_cards = {}
        recover_from_backup()
    except Exception as e:
        logging.error(f"Unexpected error loading player cards: {e}")
        recover_from_backup()

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

# Save player cards to a JSON file
def save_player_cards() -> None:
    max_retries = 3
    for attempt in range(max_retries):
        try:
            with open('player_cards.json', 'w') as f:
                json.dump(player_cards, f, indent=4)
            return  # Successfully saved, exit function
        except PermissionError:
            if attempt < max_retries - 1:
                logging.warning(f"Permission denied when saving player cards. Retry {attempt + 1}/{max_retries}...")
                time.sleep(2)  # Wait before retrying
            else:
                logging.error("Persistent permission denied when saving player cards after multiple attempts")
                # Create an emergency backup with a different filename
                try:
                    emergency_path = f'player_cards_emergency_{int(time.time())}.json'
                    with open(emergency_path, 'w') as f:
                        json.dump(player_cards, f, indent=4)
                    logging.info(f"Created emergency backup at {emergency_path}")
                except Exception as e:
                    logging.error(f"Failed to create emergency backup: {e}")
        except Exception as e:
            logging.error(f"Error saving player cards: {e}")
            break  # Exit on non-permission errors

# Backup creation
backup_folder = "backup_folder"
os.makedirs(backup_folder, exist_ok=True)
MAX_BACKUPS = 6

def create_backup():
    try:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"player_cards_backup_{timestamp}.json"
        backup_filepath = os.path.join(backup_folder, backup_filename)
        shutil.copy('player_cards.json', backup_filepath)
        logging.info(f"Created backup: {backup_filename} in {backup_filepath}")

        backup_files = [f for f in os.listdir(backup_folder) if f.startswith("player_cards_backup_")]
        backup_files.sort(reverse=True)

        if len(backup_files) > MAX_BACKUPS:
            for old_file in backup_files[MAX_BACKUPS:]:
                old_filepath = os.path.join(backup_folder, old_file)
                os.remove(old_filepath)
                logging.info(f"Removed old backup: {old_file}")
    except Exception as e:
        logging.error(f"Failed to create backup: {e}")

@tasks.loop(hours=8)
async def backup_player_data():
    logging.info("Running scheduled backup of player data")
    create_backup()

def user_has_card(user_id: str, card_name: str) -> bool:
    card_name = card_name.lower()
    for card in player_cards.get(user_id, []):
        card_aliases = next((c.get('aliases', []) for c in cards if c['name'].lower() == card.lower()), [])
        if card_name == card.lower() or card_name in [alias.lower() for alias in card_aliases]:
            return True
    return False

# Button that hopefully does the button work
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

# The embed for the !progress command
class ProgressView(View):
    def __init__(self, user_cards, missing_cards, user):
        super().__init__(timeout=None)
        self.user_cards = user_cards  
        self.unique_user_cards = list(set(user_cards)) #remove duplicates
        self.missing_cards = missing_cards
        self.user = user
        self.current_page = 0
        self.viewing_owned = True  # Start by viewing owned cards
        
        # Calculate pages needed for owned cards
        self.owned_pages = max(1, (len(self.unique_user_cards) + 9) // 10)  # At least 1 page
        
        # Calculate pages needed for missing cards
        self.missing_pages = max(1, (len(self.missing_cards) + 9) // 10)  # At least 1 page
        
        # Total pages across both sections
        self.total_pages = self.owned_pages + self.missing_pages
        
        self.update_buttons()

    def create_embed(self):
        if self.viewing_owned:
            return self.create_owned_embed()
        else:
            return self.create_missing_embed()
    
    def update_buttons(self):
        self.clear_items()
        
        # Previous page button
        if self.current_page > 0:
            prev_button = Button(label="Previous", style=discord.ButtonStyle.primary, emoji="⬅️")
            prev_button.callback = self.previous_page
            self.add_item(prev_button)
        
        # Toggle between owned and missing cards
        toggle_label = "View Missing Cards" if self.viewing_owned else "View Owned Cards"
        toggle_button = Button(label=toggle_label, style=discord.ButtonStyle.secondary, emoji="🔄")
        toggle_button.callback = self.toggle_view
        self.add_item(toggle_button)
        
        # Next page button
        if (self.viewing_owned and self.current_page < self.owned_pages - 1) or \
           (not self.viewing_owned and self.current_page < self.missing_pages - 1):
            next_button = Button(label="Next", style=discord.ButtonStyle.primary, emoji="➡️")
            next_button.callback = self.next_page
            self.add_item(next_button)

    async def toggle_view(self, interaction: discord.Interaction):
        if interaction.user != self.user:
            await interaction.response.send_message("You can't control this menu, sorry!", ephemeral=True)
            return
            
        self.viewing_owned = not self.viewing_owned
        self.current_page = 0  # Reset to first page when toggling view
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
            
    def create_owned_embed(self):
        embed = discord.Embed(
            title="📚 Card Collection Progress",
            description=f"Showing your owned unique cards ({len(set(self.unique_user_cards))}/{len(set(self.unique_user_cards)) + len(self.missing_cards)} unique cards collected)",
            color=discord.Color.green()
        )
        start = self.current_page * 10
        end = min(start + 10, len(self.user_cards))
        
        if self.user_cards:
            # Count occurrences of each card
            card_counts = Counter(self.user_cards)
            owned_cards = "\n".join([f"\u2022 {card} x{count}" if count > 1 else f"\u2022 {card}" 
                                     for card, count in card_counts.items()][start:end])
            embed.add_field(name="📋 Your Cards", value=owned_cards, inline=False)
        else:
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

# The trading hall
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
                return

    async def update_trade_status(self):
        """Update the trade status embed"""
        if not self.active:
            return
        
        def format_card_with_rarity(card_name):
            card_data = next((c for c in cards if c['name'] == card_name), None)
            if not card_data:
                return card_name
            
            # Lower rarity % means rarer card
            rarity = card_data.get('rarity', 100)
            if rarity < 5:  # Very rare cards
                return f"{card_name} 🌟"
            elif rarity < 10:  # Rare cards
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
            value="• Use `!trade_add [card]` to add cards to your offer\n"
                "• Use `!trade_remove [card]` to remove cards\n"
                "• Use `!trade_confirm` when you're satisfied with the deal\n"
                "• Use `!trade_cancel` to cancel the trade",
            inline=False
        )

        try:
            await self.trade_message.edit(embed=embed)
        except discord.NotFound:
            self.trade_message = await self.ctx.send(embed=embed)
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

            embed.set_footer(text="Trade will complete in 20 seconds. Type !trade_cancel to stop.")

            await self.ctx.send(embed=embed)

            self.finalization_time = time.time()
            await asyncio.sleep(20)  # Allow 20 seconds for final confirmation

            if not self.active:
                return

            try:
                for card in self.initiator_cards:
                    player_cards[self.initiator_id].remove(card)
                    player_cards.setdefault(self.recipient_id, []).append(card)

                for card in self.recipient_cards:
                    player_cards[self.recipient_id].remove(card)
                    player_cards.setdefault(self.initiator_id, []).append(card)

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
        if interaction.user.id != self.trade_session.recipient.id:
            await interaction.response.send_message("This trade invitation isn't for you!", ephemeral=True)
            return
        
        await interaction.response.send_message("You declined the trade.")
        await self.trade_session.cancel_trade(f"{interaction.user.mention} declined the trade.")

# List of allowed server IDs
allowed_guilds = [int(channel_id), int(test_channel_id)]

@bot.event
async def on_guild_join(guild):
    if guild.id not in allowed_guilds:
        logging.warning(f"Unauthorized guild joined: {guild.name} (ID: {guild.id}). Leaving the server.")
        if guild.system_channel:
            await guild.system_channel.send("This bot is restricted to specific servers. Leaving now.")
        await guild.leave()
    else:
        logging.info(f"Joined authorized guild: {guild.name} (ID: {guild.id}).")

# Part that does rarity
def weighted_random_choice(cards: list[dict]) -> dict:
    total = sum(card['rarity'] for card in cards)
    r = random.uniform(0, total)
    upto = 0
    for card in cards:
        upto += card['rarity']
        if upto >= r:
            return card
    return None

# Command to change the spawn mode
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

# Part that holds the timer and the channel where the card spawns
last_spawned_card = None
spawned_messages = []

@tasks.loop(minutes=45)
async def spawn_card():
    global last_spawned_card, spawned_messages
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

        # Select a card that's different from the last one
        card = select_random_card()
        
        logging.info(f"Selected card: {card['name']}")
        embed = discord.Embed(title=f"A wild card has appeared!", description="Click the button below to catch it!")
        embed.set_image(url=card['spawn_image_url'])
        
        # Send to all valid channels
        for channel in channels:
            try:
                msg = await channel.send(embed=embed, view=CatchView(card['name']), allowed_mentions=discord.AllowedMentions.none())
                spawned_messages.append(msg)
                logging.info(f"Card spawned in channel {channel.id}")
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
                await channel.send("An error occurred while spawning a card. The game will continue shortly.")
            except:
                pass

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
        main_channel = bot.get_channel(int(channel_id))
        if main_channel:
            channels.append(main_channel)
        else:
            logging.error(f"Main channel {channel_id} not found.")
    
    return channels

def select_random_card():
    """Select a random card different from the last one"""
    global last_spawned_card
    card = weighted_random_choice(cards)
    retry_count = 0
    max_retries = 5  # Prevent infinite loop
    
    while card == last_spawned_card and retry_count < max_retries:
        card = weighted_random_choice(cards)
        retry_count += 1
    
    last_spawned_card = card
    return card

# Command to print the stats of a card
@bot.command(name='stats', help="Show the stats of a specific card.")
async def print_stats(ctx, *, card_name: str):
    card = next((card for card in cards if card_name.lower() == card["name"].lower() or card_name in [alias.lower() for alias in card.get("aliases", [])]), None)
    if card:
        embed = discord.Embed(title=f"Stats for {card['name']}", description="")
        embed.add_field(name="Aliases", value=", ".join(card.get("aliases", [])), inline=False)
        embed.add_field(name="Health", value=card["health"], inline=True)
        embed.add_field(name="Damage", value=card["damage"], inline=True)
        embed.add_field(name="Rarity", value=f"{card['rarity']}%", inline=True)
        embed.add_field(name="Description", value = card["description"], inline=False)
        #embed.add_field(name="Description", value=card["description"], inline=False) add later when all cards have a description
        await ctx.send(embed=embed)
    else:
        await ctx.send("Card not found.")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        await ctx.send(f"Command not found. Use `!commands_dex` to see available commands.")
    elif isinstance(error, commands.MissingRequiredArgument):
        param = error.param.name
        await ctx.send(f"Missing required argument: `{param}`. Check command usage with `!commands_dex`.")
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
        await ctx.send("Too many arguments provided. Check command usage with `!commands_dex`.")
    elif isinstance(error, commands.CheckFailure):
        if not any(msg in str(error) for msg in ["blacklisted", "test mode"]):
            await ctx.send("You do not have permission to use this command.")
    elif isinstance(error, commands.UserInputError):
        await ctx.send("There was an error with your input. Please check the command syntax.")
    else:
        logging.error(f"Unhandled error: {error}", exc_info=error)
        await ctx.send("An unexpected error occurred. The developers have been notified.")

def validate_card_data():
    """Validate that all cards have required fields"""
    required_fields = ['name', 'health', 'damage', 'rarity', 'spawn_image_url', 'card_image_url', 'aliases']
    for i, card in enumerate(cards):
        missing_fields = [field for field in required_fields if field not in card]
        if missing_fields:
            logging.warning(f"Card #{i} ({card.get('name', 'Unknown')}) is missing fields: {', '.join(missing_fields)}")
        
        # Check for valid URLs
        for url_field in ['spawn_image_url', 'card_image_url']:
            if url_field in card and not card[url_field].startswith(('http://', 'https://')):
                logging.warning(f"Card {card.get('name', 'Unknown')} has invalid {url_field}: {card[url_field]}")

# When the bot is ready, it prints to the console that it's online
@bot.event
async def on_ready():
    global spawned_messages
    load_player_cards()  # Load player cards when the bot starts
    validate_card_data()
    print(f'We have logged in as {bot.user}')
    logging.info("Logging is configured correctly.")
    
    # Send online message to both channels
    channels = [bot.get_channel(int(channel_id)), bot.get_channel(int(test_channel_id))]
    logging.info(f"Attempting to send online message to channels: {channel_id}, {test_channel_id}")
    for channel in channels:
        if channel:
            try:
                await channel.send("235th dex is online! Type !commands_dex to see the available commands.")
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

# see_card command to see a specific card
@bot.command(name='see_card')
async def see_card(ctx, *, card_name: str):
    user_id = str(ctx.author.id)  # Ensure user ID is a string
    
    if user_id in player_cards and player_cards[user_id]:
        card_name = card_name.strip().lower()
        user_card = next((card for card in player_cards[user_id] if card.lower() == card_name or card_name in [alias.lower() for alias in next(c.get('aliases', []) for c in cards if c['name'].lower() == card.lower())]), None)
        if user_card:
            selected_card = next(card for card in cards if card["name"].lower() == card_name or card_name in [alias.lower() for alias in card.get("aliases", [])])
            embed = discord.Embed(title=f"Here's your {selected_card['name']}", description="")
            embed.set_image(url=selected_card["card_image_url"])
            await ctx.send(embed=embed)
        else:
            await ctx.send("You don't have this card.")
    else:
        await ctx.send("You haven't caught any cards yet.")

# Command that shows the user's progress
@bot.command(name='progress')
async def progress(ctx):
    user_id = str(ctx.author.id)
    total_cards = len(cards)
    user_cards = player_cards.get(user_id, [])
    missing_cards = [card['name'] for card in cards if card['name'] not in user_cards]

    view = ProgressView(user_cards, missing_cards, ctx.author)
    view.message = await ctx.send(embed=view.create_embed(), view=view)

@bot.command(name='view_progress', help="Admin command to view another user's collection progress")
@commands.check(is_authorized)
async def view_progress(ctx, user: discord.Member):
    """
    Allows authorized users to view the card collection progress of any user.
    Usage: !view_progress @username
    """
    target_user_id = str(user.id)
    total_cards = len(cards)
    user_cards = player_cards.get(target_user_id, [])
    
    if not user_cards:
        await ctx.send(f"{user.display_name} hasn't collected any cards yet.")
        return
    
    # Count total unique cards (no duplicates)
    unique_cards = set(user_cards)
    # Get card duplicates info
    card_counts = Counter(user_cards)
    # Calculate duplicates
    total_duplicates = len(user_cards) - len(unique_cards)
    
    # Find missing cards
    missing_cards = [card['name'] for card in cards if card['name'] not in user_cards]
    
    # Find rarest card owned by rarity value
    card_rarity = {card['name']: card['rarity'] for card in cards}
    if user_cards:
        rarest_card = min(set(user_cards), key=lambda card: card_rarity.get(card, float('inf')))
        most_duplicated_card = card_counts.most_common(1)[0][0] if total_duplicates > 0 else "None"
    else:
        rarest_card = "None"
        most_duplicated_card = "None"
    
    # Create the embed
    embed = discord.Embed(
        title=f"📊 Card Collection Stats for {user.display_name}",
        description=f"Collection progress: {len(unique_cards)}/{total_cards} unique cards ({len(unique_cards)/total_cards*100:.1f}%)",
        color=discord.Color.blue()
    )
    
    # Add collection stats
    embed.add_field(name="Total Cards", value=f"{len(user_cards)} (including duplicates)", inline=True)
    embed.add_field(name="Unique Cards", value=f"{len(unique_cards)}", inline=True)
    embed.add_field(name="Duplicates", value=f"{total_duplicates}", inline=True)
    
    # Add interesting stats
    embed.add_field(name="Rarest Card Owned", value=rarest_card, inline=True)
    embed.add_field(name="Most Duplicated", value=f"{most_duplicated_card} ({card_counts[most_duplicated_card]}x)" if most_duplicated_card != "None" else "None", inline=True)
    embed.add_field(name="Missing Cards", value=f"{len(missing_cards)}", inline=True)
    
    # Create collection view for the specified user
    view = ProgressView(user_cards, missing_cards, ctx.author)  # Note: controls belong to command invoker
    
    # Send the statistics and view
    embed.set_footer(text="Use the buttons below to navigate cards")
    message = await ctx.send(embed=embed)
    
    # Send the detailed card view in a second message
    view.message = await ctx.send(embed=view.create_embed(), view=view)
    
    logging.info(f"Admin {ctx.author} viewed collection progress for {user.display_name}")

@bot.command(name='give')
@requires_valid_user()
async def give_card(ctx, card: str, receiving_user: discord.Member):
    sender_id = str(ctx.author.id)
    receiver_id = str(receiving_user.id)
    card_lower = card.lower()
    
    async with battle_lock:  # Use the lock to prevent race conditions
        try:
            sender_cards = player_cards.get(sender_id, [])
            if not any(card_lower == c.lower() or card_lower in [alias.lower() for alias in next((card['aliases'] for card in cards if card['name'].lower() == c.lower()), [])] for c in sender_cards):
                await ctx.send(f"You don't own the card `{card}`.")
                return
            
            # Find the exact card name (preserving case)
            actual_card_name = next((c for c in sender_cards if card_lower == c.lower() or card_lower in [alias.lower() for alias in next((card['aliases'] for card in cards if card['name'].lower() == c.lower()), [])]), None)
            if not actual_card_name:
                await ctx.send(f"Error finding card `{card}` in your inventory.")
                return
                
            # Remove the card from the sender's inventory
            sender_cards.remove(actual_card_name)

            # Add the card to the receiver's inventory
            receiver_cards = player_cards.setdefault(receiver_id, [])
            receiver_cards.append(actual_card_name)

            # Save immediately after transaction
            save_player_cards()
            await ctx.send(f"{ctx.author.mention} has given `{actual_card_name}` to {receiving_user.mention}.")
            logging.info(f"{ctx.author} gave {actual_card_name} to {receiving_user}.")
        except Exception as e:
            logging.error(f"Error in card transfer: {e}", exc_info=True)
            await ctx.send("An error occurred during card transfer.")

# Command to spawn a certain card
@bot.command(name='spawn_card', help="Spawn a specific card.")
@commands.check(is_authorized)
async def spawn_card_command(ctx, *, args: str):
    args = args.strip().lower()
    
    # Check if 'test' is in the arguments
    use_test_channel = False
    if args.endswith(' test'):
        use_test_channel = True
        card_name = args[:-5].strip()  # Remove ' test' from the end
    else:
        card_name = args
    
    # Validate card name
    if not all(c.isalnum() or c.isspace() or c in ["'", "-"] for c in card_name):
        await ctx.send("Invalid card name. Only alphanumeric characters, spaces, apostrophes, and hyphens are allowed.")
        return

    card = next((card for card in cards if card_name == card["name"].lower() or card_name in [alias.lower() for alias in card.get("aliases", [])]), None)
    if card:
        # Choose the channel based on the 'test' parameter
        if use_test_channel:
            channel = bot.get_channel(int(test_channel_id))
            channel_name = "test channel"
        else:
            channel = bot.get_channel(int(channel_id))
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

@bot.command(name='battle', help="Battle another player with your cards.")
@requires_valid_user()
async def battle(ctx, opponent: discord.Member = None):
    try:
        if not opponent:
            await ctx.send("Please specify an opponent to battle with. Usage: `!battle @user`")
            return
            
        if opponent.id == ctx.author.id:
            await ctx.send("You can't battle yourself!")
            return
        
        if opponent.bot:
            await ctx.send("You can't battle a bot!")
            return
        
        challenger_id = str(ctx.author.id)
        opponent_id = str(opponent.id)

        # Check if players have cards
        if challenger_id not in player_cards or not player_cards[challenger_id]:
            await ctx.send("You don't have any cards to battle with!")
            return
        
        if opponent_id not in player_cards or not player_cards[opponent_id]:
            await ctx.send(f"{opponent.display_name} doesn't have any cards to battle with!")
            return
        
        # Initialize trackers if not exist
        if not hasattr(bot, 'ongoing_battles'):
            bot.ongoing_battles = set()
        
        if not hasattr(bot, 'active_battles'):
            bot.active_battles = []

        # Check if players are in battles
        if challenger_id in bot.ongoing_battles:
            await ctx.send("You're already in a battle!")
            return
            
        if opponent_id in bot.ongoing_battles:
            await ctx.send(f"{opponent.display_name} is already in a battle!")
            return

        # Add both players to ongoing battles
        bot.ongoing_battles.add(challenger_id)
        bot.ongoing_battles.add(opponent_id)
        
        # Create and start battle
        battle = CardBattle(ctx, ctx.author, opponent)
        bot.active_battles.append(battle)
        await battle.start_battle()
        
    except discord.NotFound:
        await ctx.send("Could not find the specified user.")
    except discord.Forbidden:
        await ctx.send("I don't have permission to interact with one of the players.")
    except Exception as e:
        logging.error(f"Battle error: {e}", exc_info=True)
        await ctx.send("An error occurred while setting up the battle.")
    finally:
        # Clean up in case of error
        bot.ongoing_battles.discard(challenger_id)
        bot.ongoing_battles.discard(opponent_id)
        if 'battle' in locals() and battle in getattr(bot, 'active_battles', []):
            bot.active_battles.remove(battle)

@bot.command(name='battle_ready', help="Confirm your battle card selection")
async def battle_ready(ctx):
    user_id = str(ctx.author.id)
    
    # Check if the user is in a battle
    if not hasattr(bot, 'ongoing_battles') or user_id not in bot.ongoing_battles:
        await ctx.send("You're not in an active battle!")
        return
    
    # Find the active battle for this user
    active_battle = None
    for battle in getattr(bot, 'active_battles', []):
        if battle.challenger_id == user_id:
            active_battle = battle
            player_type = "challenger"
            break
        elif battle.opponent_id == user_id:
            active_battle = battle
            player_type = "opponent"
            break
    
    if not active_battle:
        await ctx.send("Couldn't find your active battle.")
        return
    
    # Check if cards were selected
    selection_attr = f"{player_type}_cards"
    current_selection = getattr(active_battle, selection_attr, [])
    
    if not current_selection:
        await ctx.send("You haven't selected any cards yet! Use `!battle_add [card name]` to add cards.")
        return
    
    # Mark as ready
    setattr(active_battle, f"{player_type}_selected", True)
    await ctx.send(f"You're ready for battle with: {', '.join(current_selection)}! Waiting for your opponent...")

@bot.command(name='battle_add', help="Add a specific card to your active battle")
async def battle_add(ctx, *, card_name: str):
    user_id = str(ctx.author.id)
    
    # Check if the user is in a battle
    if not hasattr(bot, 'ongoing_battles') or user_id not in bot.ongoing_battles:
        await ctx.send("You're not in an active battle!")
        return
    
    # Find the active battle for this user
    active_battle = None
    for battle in getattr(bot, 'active_battles', []):
        if battle.challenger_id == user_id:
            active_battle = battle
            player_type = "challenger"
            break
        elif battle.opponent_id == user_id:
            active_battle = battle
            player_type = "opponent"
            break
    
    if not active_battle:
        await ctx.send("Couldn't find your active battle.")
        return
    
    # Reset activity timer when adding a card via command
    active_battle.reset_activity_timer()
    
    # Check if the user has already submitted their cards
    if (player_type == "challenger" and active_battle.challenger_selected) or \
       (player_type == "opponent" and active_battle.opponent_selected):
        await ctx.send("You've already submitted your card selection!")
        return
    
    # Check if the user has this card
    user_cards = player_cards.get(user_id, [])
    card_lower = card_name.lower()
    
    # Find the actual card with matching name (case insensitive) or aliases
    found_card = None
    for card in user_cards:
        card_data = next((c for c in cards if c['name'].lower() == card.lower()), None)
        if card.lower() == card_lower:
            found_card = card
            break
        elif card_data and 'aliases' in card_data:
            if card_lower in [alias.lower() for alias in card_data['aliases']]:
                found_card = card
                break
    
    if not found_card:
        await ctx.send(f"You don't have a card named `{card_name}`!")
        return
    
    # Check if the card is already in the battle selection
    selection_attr = f"{player_type}_cards"
    current_selection = getattr(active_battle, selection_attr, [])
    
    if found_card in current_selection:
        await ctx.send(f"`{found_card}` is already in your battle selection!")
        return
    
    # Check if user has reached the card limit
    if len(current_selection) >= 3:
        await ctx.send("You've already selected the maximum number of cards (3)!")
        return
    
    # Add the card to the battle selection
    current_selection.append(found_card)
    setattr(active_battle, selection_attr, current_selection)
    
    # Provide feedback
    if len(current_selection) == 3:
        await ctx.send(f"Added `{found_card}` to your battle selection. Your team is complete! Cards: {', '.join(current_selection)}\n\nReady to fight? Type `!battle_ready` to confirm your selection.")
    else:
        await ctx.send(f"Added `{found_card}` to your battle selection. You have selected {len(current_selection)}/3 cards: {', '.join(current_selection)}")

@bot.command(name='battle_cards', help="See your currently selected battle cards")
async def battle_cards(ctx):
    user_id = str(ctx.author.id)
    
    # Check if the user is in a battle
    if not hasattr(bot, 'ongoing_battles') or user_id not in bot.ongoing_battles:
        await ctx.send("You're not in an active battle!")
        return
    
    # Find the active battle for this user
    active_battle = None
    for battle in getattr(bot, 'active_battles', []):
        if battle.challenger_id == user_id:
            active_battle = battle
            player_type = "challenger"
            break
        elif battle.opponent_id == user_id:
            active_battle = battle
            player_type = "opponent"
            break
    
    if not active_battle:
        await ctx.send("Couldn't find your active battle.")
        return
        
    # Get selected cards
    selection_attr = f"{player_type}_cards"
    current_selection = getattr(active_battle, selection_attr, [])
    
    if not current_selection:
        await ctx.send("You haven't selected any cards yet! Use `!battle_add [card name]` to add cards.")
    else:
        cards_str = "\n".join([f"• {card}" for card in current_selection])
        await ctx.send(f"Your selected battle cards ({len(current_selection)}/3):\n{cards_str}")

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
        self.timeout = 120  # 2 minutes timeout
        self.last_activity = time.time()  # Track last activity time
    
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
        self.battle_message = await self.ctx.send(embed=embed, view=view)

        # Wait for acceptance and card selection
        selection_complete = await self.wait_for_selection()
        
        # If wait_for_selection returns False, we timed out
        if not selection_complete:
            # Disable the view buttons when timing out
            for child in view.children:
                child.disabled = True
            await self.battle_message.edit(view=view)
            await self.ctx.send("Battle invitation timed out due to inactivity.")
            return
        
        # Both players have selected cards, begin the battle
        if self.challenger_selected and self.opponent_selected:
            # Send a "preparing battle" message
            await self.ctx.send(f"Both players have selected their cards! Preparing for battle...")
            await asyncio.sleep(2)  # Short dramatic pause
            await self.execute_battle()
        else:
            # This should not happen due to the wait_for_selection, but just in case
            await self.ctx.send("Battle cancelled.")
    
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
        challenger_cards_str = "\n".join([f"• **{card['name']}** (❤️ {card['health']}, ⚔️ {card['damage']})" 
                                        for card in challenger_battle_cards])
        opponent_cards_str = "\n".join([f"• **{card['name']}** (❤️ {card['health']}, ⚔️ {card['damage']})" 
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
            damage = attacking_card['damage']
            
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
        else:
            winner = self.opponent
            loser = self.challenger

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
                'damage': original_card.get('damage', original_card.get('attack', 1))
            }
        # Fallback in case the card isn't found
        return {
            'name': card_name,
            'health': 1,
            'damage': 1
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
        if interaction.user.id != self.battle.opponent.id:
            await interaction.response.send_message("This challenge isn't for you!", ephemeral=True)
            return
            
        await interaction.response.send_message("You declined the battle.", ephemeral=True)
        await self.battle.ctx.send(f"{interaction.user.mention} declined the battle challenge.")
        
        # Set flags so the battle terminates
        self.battle.challenger_selected = True
        self.battle.opponent_selected = True
        
        # Disable the buttons
        for item in self.children:
            item.disabled = True
        
        await self.battle.battle_message.edit(view=self)

# Extend the CardBattle class with card selection methods
async def challenger_card_selection(self, user):
    """Let challenger select their battle cards"""
    user_cards = player_cards.get(str(user.id), [])
    unique_cards = list(set(user_cards))
    
    # Send DM with card selection
    try:
        dm_channel = await user.create_dm()
        
        # Create card selection view
        view = CardSelectionView(self, user, "challenger", unique_cards)
        embed = discord.Embed(
            title="Select Your Battle Cards",
            description="Choose up to 3 cards for battle.\nClick Submit when you're done.",
            color=discord.Color.blue()
        )
        await dm_channel.send(embed=embed, view=view)
    except discord.Forbidden:
        await self.ctx.send(f"{user.mention} I can't send you a DM. Please enable DMs from server members.")
        self.challenger_selected = True
        self.opponent_selected = True  # Force battle termination

async def opponent_card_selection(self, user):
    """Let opponent select their battle cards"""
    user_cards = player_cards.get(str(user.id), [])
    unique_cards = list(set(user_cards))
    
    # Send DM with card selection
    try:
        dm_channel = await user.create_dm()
        
        # Create card selection view
        view = CardSelectionView(self, user, "opponent", unique_cards)
        embed = discord.Embed(
            title="Select Your Battle Cards",
            description="Choose up to 3 cards for battle.\nClick Submit when you're done.",
            color=discord.Color.blue()
        )
        await dm_channel.send(embed=embed, view=view)
    except discord.Forbidden:
        await self.ctx.send(f"{user.mention} I can't send you a DM. Please enable DMs from server members.")
        self.challenger_selected = True
        self.opponent_selected = True  # Force battle termination

# Add these methods to the CardBattle class
CardBattle.challenger_card_selection = challenger_card_selection
CardBattle.opponent_card_selection = opponent_card_selection

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
                attack_value = card_data.get('damage', card_data.get('attack', 1))
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

@bot.command(name='battle_help', help="Explains how to battle with cards")
async def battle_help(ctx):
    embed = discord.Embed(
        title="Card Battle Help",
        description="How to battle with your cards",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="Starting a Battle",
        value="Use `!battle @user` to challenge another player",
        inline=False
    )
    
    embed.add_field(
        name="Selecting Cards",
        value="After the opponent accepts, both players can select cards with:\n"
              "• Use dropdown menus in the selection dialog OR\n"
              "• Type `!battle_add [card name]` to add a specific card\n"
              "You can select up to 3 cards.",
        inline=False
    )
    
    embed.add_field(
        name="Confirming Selection", 
        value="After adding cards with `!battle_add`, use `!battle_ready` to confirm your selection",
        inline=False
    )
    
    embed.add_field(
        name="Battle Process",
        value="Cards will automatically take turns attacking until one side has no cards left.",
        inline=False
    )
    
    await ctx.send(embed=embed)

# The trading hall commands
@bot.command(name='trade')
@requires_valid_user()
async def trade_command(ctx, recipient: discord.Member = None):
    if not recipient:
        await ctx.send("Please specify a user to trade with. Usage: `!trade @user`")
        return
    
    initiator_id = str(ctx.author.id)
    recipient_id = str(recipient.id)

    # Check if players have cards
    if initiator_id not in player_cards or not player_cards[initiator_id]:
        await ctx.send("You don't have any cards to trade!")
        return
    
    if recipient_id not in player_cards or not player_cards[recipient_id]:
        await ctx.send(f"{recipient.display_name} doesn't have any cards to trade!")
        return
    
    # Initialize trade sessions tracker if not exist
    if not hasattr(bot, 'active_trades'):
        bot.active_trades = {}
    
    # Check if users are already in active trades
    if initiator_id in bot.active_trades:
        await ctx.send("You're already in an active trade!")
        return
        
    if recipient_id in bot.active_trades:
        await ctx.send(f"{recipient.display_name} is already in an active trade!")
        return

    # Create and start trade
    trade_session = TradeSession(ctx, ctx.author, recipient)
    
    # Register the active trade
    bot.active_trades[initiator_id] = trade_session
    bot.active_trades[recipient_id] = trade_session
    
    await trade_session.start_trade()

@bot.command(name='trade_add', help="Add a card to your trade offer")
async def trade_add(ctx, *, card_name: str):
    user_id = str(ctx.author.id)
    
    # Check if user is in a trade
    if not hasattr(bot, 'active_trades') or user_id not in bot.active_trades:
        await ctx.send("You're not in an active trade!")
        return
    
    trade = bot.active_trades[user_id]
    
    # Reset activity timer
    trade.reset_activity_timer()
    
    # Check if the trade is still active
    if not trade.active:
        await ctx.send("That trade is no longer active.")
        if user_id in bot.active_trades:
            del bot.active_trades[user_id]
        return
    
    # Determine if user is initiator or recipient
    is_initiator = (user_id == trade.initiator_id)
    
    # Check if user has already confirmed
    if (is_initiator and trade.initiator_confirmed) or (not is_initiator and trade.recipient_confirmed):
        await ctx.send("You've already confirmed the trade! Use `!trade_unconfirm` to make changes.")
        return
    
    # Check if the user has this card
    user_cards = player_cards.get(user_id, [])
    card_lower = card_name.lower()
    
    # Find the actual card with matching name (case insensitive) or aliases
    found_card = None
    for card in user_cards:
        card_data = next((c for c in cards if c['name'].lower() == card.lower()), None)
        if card.lower() == card_lower:
            found_card = card
            break
        elif card_data and 'aliases' in card_data:
            if card_lower in [alias.lower() for alias in card_data['aliases']]:
                found_card = card
                break
    
    if not found_card:
        await ctx.send(f"You don't have a card named `{card_name}`!")
        return
    
    # Add card to appropriate list
    if is_initiator:
        if found_card in trade.initiator_cards:
            await ctx.send(f"You've already added `{found_card}` to the trade!")
            return
        trade.initiator_cards.append(found_card)
    else:
        if found_card in trade.recipient_cards:
            await ctx.send(f"You've already added `{found_card}` to the trade!")
            return
        trade.recipient_cards.append(found_card)
    
    await ctx.send(f"Added `{found_card}` to your trade offer.")
    await trade.update_trade_status()

@bot.command(name='trade_remove', help="Remove a card from your trade offer")
async def trade_remove(ctx, *, card_name: str):
    user_id = str(ctx.author.id)
    
    # Check if user is in a trade
    if not hasattr(bot, 'active_trades') or user_id not in bot.active_trades:
        await ctx.send("You're not in an active trade!")
        return
    
    trade = bot.active_trades[user_id]
    
    # Reset activity timer
    trade.reset_activity_timer()
    
    # Check if the trade is still active
    if not trade.active:
        await ctx.send("That trade is no longer active.")
        if user_id in bot.active_trades:
            del bot.active_trades[user_id]
        return
    
    # Determine if user is initiator or recipient
    is_initiator = (user_id == trade.initiator_id)
    
    # Check if user has already confirmed
    if (is_initiator and trade.initiator_confirmed) or (not is_initiator and trade.recipient_confirmed):
        await ctx.send("You've already confirmed the trade! Use `!trade_unconfirm` to make changes.")
        return
    
    card_lower = card_name.lower()
    
    # Get the user's cards in the trade
    user_trade_cards = trade.initiator_cards if is_initiator else trade.recipient_cards
    
    # Find the card to remove
    card_to_remove = None
    for card in user_trade_cards:
        card_data = next((c for c in cards if c['name'].lower() == card.lower()), None)
        if card.lower() == card_lower:
            card_to_remove = card
            break
        elif card_data and 'aliases' in card_data:
            if card_lower in [alias.lower() for alias in card_data['aliases']]:
                card_to_remove = card
                break
    
    if not card_to_remove:
        await ctx.send(f"You don't have `{card_name}` in your trade offer!")
        return
    
    # Remove the card
    user_trade_cards.remove(card_to_remove)
    await ctx.send(f"Removed `{card_to_remove}` from your trade offer.")
    await trade.update_trade_status()

@bot.command(name='trade_confirm', help="Confirm your side of the trade")
async def trade_confirm(ctx):
    user_id = str(ctx.author.id)
    
    # Check if user is in a trade
    if not hasattr(bot, 'active_trades') or user_id not in bot.active_trades:
        await ctx.send("You're not in an active trade!")
        return
    
    trade = bot.active_trades[user_id]
    
    # Reset activity timer
    trade.reset_activity_timer()
    
    # Check if the trade is still active
    if not trade.active:
        await ctx.send("That trade is no longer active.")
        if user_id in bot.active_trades:
            del bot.active_trades[user_id]
        return
    
    # Determine if user is initiator or recipient
    is_initiator = (user_id == trade.initiator_id)
    
    # Set confirmation flag
    if is_initiator:
        trade.initiator_confirmed = True
    else:
        trade.recipient_confirmed = True
    
    await ctx.send(f"{ctx.author.mention} has confirmed the trade!")
    await trade.update_trade_status()
    
    # Check if both users have confirmed
    if trade.initiator_confirmed and trade.recipient_confirmed:
        await trade.finalize_trade()
        # Clean up
        if trade.initiator_id in bot.active_trades:
            del bot.active_trades[trade.initiator_id]
        if trade.recipient_id in bot.active_trades:
            del bot.active_trades[trade.recipient_id]

@bot.command(name='trade_unconfirm', help="Remove your confirmation of the trade")
async def trade_unconfirm(ctx):
    user_id = str(ctx.author.id)
    
    # Check if user is in a trade
    if not hasattr(bot, 'active_trades') or user_id not in bot.active_trades:
        await ctx.send("You're not in an active trade!")
        return
    
    trade = bot.active_trades[user_id]
    
    # Reset activity timer
    trade.reset_activity_timer()
    
    # Check if the trade is still active
    if not trade.active:
        await ctx.send("That trade is no longer active.")
        if user_id in bot.active_trades:
            del bot.active_trades[user_id]
        return
    
    # Determine if user is initiator or recipient
    is_initiator = (user_id == trade.initiator_id)
    
    # Check if user has confirmed
    if (is_initiator and not trade.initiator_confirmed) or (not is_initiator and not trade.recipient_confirmed):
        await ctx.send("You haven't confirmed the trade yet!")
        return
    
    # Remove confirmation
    if is_initiator:
        trade.initiator_confirmed = False
    else:
        trade.recipient_confirmed = False
    
    await ctx.send(f"{ctx.author.mention} has withdrawn their confirmation.")
    await trade.update_trade_status()

@bot.command(name='trade_cancel', help="Cancel the current trade")
async def trade_cancel(ctx):
    user_id = str(ctx.author.id)
    
    # Check if user is in a trade
    if not hasattr(bot, 'active_trades') or user_id not in bot.active_trades:
        await ctx.send("You're not in an active trade!")
        return
    
    trade = bot.active_trades[user_id]
    
    # Check if the trade is still active
    if not trade.active:
        await ctx.send("That trade is no longer active.")
        if user_id in bot.active_trades:
            del bot.active_trades[user_id]
        return
    
    # Cancel the trade
    await trade.cancel_trade(f"Trade cancelled by {ctx.author.mention}")
    
    # Clean up
    if trade.initiator_id in bot.active_trades:
        del bot.active_trades[trade.initiator_id]
    if trade.recipient_id in bot.active_trades:
        del bot.active_trades[trade.recipient_id]

@bot.command(name='trade_status', help="Check the status of your current trade")
async def trade_status(ctx):
    user_id = str(ctx.author.id)
    
    # Check if user is in a trade
    if not hasattr(bot, 'active_trades') or user_id not in bot.active_trades:
        await ctx.send("You're not in an active trade!")
        return
    
    trade = bot.active_trades[user_id]
    
    # Reset activity timer
    trade.reset_activity_timer()
    
    # Check if the trade is still active
    if not trade.active:
        await ctx.send("That trade is no longer active.")
        if user_id in bot.active_trades:
            del bot.active_trades[user_id]
        return
    
    # Just update the trade status
    await trade.update_trade_status()

@bot.command(name='trade_help', help="Get help with the trade system")
async def trade_help(ctx):
    embed = discord.Embed(
        title="Card Trading Help",
        description="How to trade cards with other players",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="Starting a Trade",
        value="Use `!trade @user` to start trading with another player",
        inline=False
    )
    
    embed.add_field(
        name="Adding Cards",
        value="Use `!trade_add [card name]` to add a card to your trade offer",
        inline=False
    )
    
    embed.add_field(
        name="Removing Cards",
        value="Use `!trade_remove [card name]` to remove a card from your offer",
        inline=False
    )
    
    embed.add_field(
        name="Confirming Trade", 
        value="Use `!trade_confirm` when you're happy with the deal\n"
              "Both players must confirm for the trade to complete",
        inline=False
    )
    
    embed.add_field(
        name="Other Commands",
        value="• `!trade_unconfirm` - Remove your confirmation\n"
              "• `!trade_cancel` - Cancel the trade entirely\n"
              "• `!trade_status` - Check the current status of your trade",
        inline=False
    )
    
    await ctx.send(embed=embed)

#///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
#other commands not related to the card game
#///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////

# Respond to a simple message
@bot.command(name='hello')
async def hello(ctx):
    await ctx.send('Hello! I am the 235th dex! At your service!')

# Gives a random number between 0 and 10000000
@bot.command(name='random_number',help="Gives a random number.")
async def random_number(ctx):
    random_number = random.randint(0, 10000000)
    await ctx.send(f'Your random number is: {random_number}')

@bot.command(name='commands_dex', help="Shows a list of all the commands you can use.")
async def list_commands(ctx):
    embed = discord.Embed(
        title="🎮 235th Dex Command Center",
        description="Here are all the commands available to you:",
        color=discord.Color.purple()
    )
    
    # General Commands
    embed.add_field(
        name="📝 General",
        value=(
            "`!hello` - Get a greeting from the bot\n"
            "`!random_number` - Generate a random number\n"
            "`!info_dex` - View information about the bot\n"
            "`!commands_dex` - Show this command list\n"
            "`!gud_boy` - Shows a good boy GIF"
        ),
        inline=False
    )
    
    # Card Collection Commands
    embed.add_field(
        name="🃏 Card Collection",
        value=(
            "`!see_card [card name]` - View a card you've caught\n"
            "`!progress` - Show your card collection progress\n"
            "`!stats [card name]` - Show stats for a specific card\n"
            "`!give [card name] [@user]` - Give a card to another user"
        ),
        inline=False
    )
    
    # Battle Commands
    embed.add_field(
        name="⚔️ Battle System",
        value=(
            "`!battle [@user]` - Challenge another user to a battle\n"
            "`!battle_add [card name]` - Add a card to your battle team\n"
            "`!battle_cards` - See your currently selected cards\n"
            "`!battle_ready` - Confirm your card selection\n"
            "`!battle_help` - Get help with the battle system"
        ),
        inline=False
    )

    embed.add_field(
        name="🔄 Trading System",
        value=(
            "`!trade [@user]` - Start a card trade with another user\n"
            "`!trade_add [card name]` - Add a card to your trade offer\n"
            "`!trade_remove [card name]` - Remove a card from your offer\n"
            "`!trade_confirm` - Confirm the trade deal\n"
            "`!trade_unconfirm` - Unconfirm the trade deal\n"
            "`!trade_status` - Check your current trade\n"
            "`!trade_help` - Get help with trading"
        ),
        inline=False
    )
    
    # Bot Stats
    embed.add_field(
        name="📊 Leaderboard",
        value="`!leaderboard` - Show general statistics about the card game",
        inline=False
    )
    
    embed.set_thumbnail(url="https://cdn.discordapp.com/app-icons/1321813254128930867/450fa2947cf99f3182797b7b503c5c63.png")

    embed.set_footer(text="Need help? Join our support server: discord.gg/yRNxTXtm")
    
    await ctx.send(embed=embed)

#info, command to show the current release
@bot.command(name='info_dex', aliases=['dex_info', 'bot_info'], help="General info about the dex")
async def info(ctx):
    # Store bot launch time
    if not hasattr(bot, 'launch_time'):
        bot.launch_time = datetime.datetime.now()

    # Calculate uptime
    uptime = datetime.datetime.now() - bot.launch_time
    days, remainder = divmod(int(uptime.total_seconds()), 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60) 
    uptime_str = f"{days}d {hours}h {minutes}m"

    # Count total users and cards
    total_users = len(player_cards)
    total_cards_collected = sum(len(cards) for cards in player_cards.values())

    # Get backup count
    backup_count = len([f for f in os.listdir(backup_folder) if f.startswith("player_cards_backup_")])

    embed = discord.Embed(
        title="235th Dex Information",
        description="Technical details and status information",
        color=discord.Color.teal()
    )

    embed.add_field(
        name="🏷️ Version",
        value="1.5.1 - \"The Trading Update\"", 
        inline=False
    )

    embed.add_field(
        name="👨‍💻 Developers",
        value="<@1035607651985403965>\n<@573878397952851988>\n<@845973389415284746>",
        inline=True
    )

    embed.add_field(
        name="📈 System Stats",
        value=f"• Users: {total_users}\n• Cards: {total_cards_collected}\n• Uptime: {uptime_str}",
        inline=True
    )

    embed.add_field(
        name="💾 Database",
        value=f"• Status: Healthy\n• Backups: {backup_count}/{MAX_BACKUPS}",
        inline=True
    )
    
    embed.add_field(
        name="📜 Latest Changes",
        value="• Bugfixes\n• Added card trading system\n• Enhanced battle system",
        inline=False
    )

    # Add timestamp
    embed.set_footer(text=f"Last updated: {datetime.datetime.now().strftime('%d-%m-%Y %H:%M')}")

    await ctx.send(embed=embed)

def count_lines_of_code() -> int:
    project_dir = '/home/container'
    total_lines = 0

    for root, _, files in os.walk(project_dir):
        for file in files:
            if file.endswith('test.py') or file.endswith('cards.py'):
                file_path = os.path.join(root, file)
                with open(file_path, 'r') as f:
                    total_lines += sum(1 for _ in f)
    return total_lines

# Command to play a certain GIF, restricted to authorized users
@bot.command(name='celebrate', help="Posts a celebration animation (admin only)")
@commands.check(is_authorized)
async def play_gif(ctx):
    embed = discord.Embed(title="Celebration Time!")
    embed.set_image(url="https://cdn.discordapp.com/attachments/1322197080625647627/1348320094660464863/image0.gif?ex=67cf0871&is=67cdb6f1&hm=d47b2a88b5fe88a4da2c03c78a94f67eb66b9efa0104c69b72c6a9006c4c95e2")
    await ctx.send(embed=embed)

# For fun interactions with the bot
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

    await bot.process_commands(message)

@bot.command(name="gud_boy", help="Shows a good boy GIF")
async def gud_boy(ctx):
    embed = discord.Embed(title="Good boy!")
    embed.set_image(url="https://cdn.discordapp.com/attachments/1258772746897461458/1340729833889464422/image0.gif?ex=67c92c35&is=67c7dab5&hm=0b58bb55cc24fbeb9e74f77ed4eedaf4d48ba68f61e82922b9632c6a61f7713b&")
    await ctx.send(embed=embed)

# Public !stats command
@bot.command(name='leaderboard', help="Show general statistics about the card game.")
async def public_stats(ctx):
    total_users = len(player_cards)
    total_cards_collected = sum(len(cards) for user_id, cards in player_cards.items() if user_id not in authorized_user_ids)
    
    # Top Collectors
    collectors = [(user_id, len(cards)) for user_id, cards in player_cards.items() if user_id not in authorized_user_ids]
    top_collectors = sorted(collectors, key=lambda x: x[1], reverse=True)[:5]
    
    # Unique Cards Leaderboard
    unique_collectors = [(user_id, len(set(cards))) for user_id, cards in player_cards.items() if user_id not in authorized_user_ids]
    top_unique_collectors = sorted(unique_collectors, key=lambda x: x[1], reverse=True)[:5]
    
    # Most Collected Card
    all_cards = [card for cards in player_cards.values() for card in cards]
    most_collected_card = Counter(all_cards).most_common(1)[0][0]
    
    # Rarest Card Owned
    card_rarity = {card['name']: card['rarity'] for card in cards}
    owned_cards = set(all_cards)
    rarest_card_owned = min(owned_cards, key=lambda card: card_rarity.get(card, float('inf')))
    
    embed = discord.Embed(title="235th Dex Statistics")
    embed.add_field(name="Total Users", value=total_users, inline=False)
    embed.add_field(name="Total Cards Collected", value=total_cards_collected, inline=False)
    embed.add_field(name="Top Collectors", value="\n".join([f"<@{user_id}>: {count} cards" for user_id, count in top_collectors]), inline=False)
    embed.add_field(name="Top Unique Card Collecters", value="\n".join([f"<@{user_id}>: {count} unique cards" for user_id, count in top_unique_collectors]), inline=False)
    embed.add_field(name="Most Collected Card", value=most_collected_card, inline=False)
    embed.add_field(name="Rarest Card Owned", value=rarest_card_owned, inline=False)
    
    await ctx.send(embed=embed)

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
                await asyncio.sleep(delay)
            else:
                logging.error(f"Failed to send embed after {retries} attempts: {e}")
                raise
        except Exception as e:
            logging.error(f"Unexpected error sending embed: {e}")
            raise

#///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
#other cool things for shutdown and signal handling

# Custom shutdown function
async def shutdown_bot():
    channels = [bot.get_channel(int(channel_id)), bot.get_channel(int(test_channel_id))]
    logging.info(f"Attempting to send disconnect message to channels: {channel_id}, {test_channel_id}")
    for channel in channels:
        if channel:
            try:
                if channel.id == int(test_channel_id):
                    if spawn_mode == 'both':
                        developer_mentions = " ".join([f"<@{user_id}>" for user_id in authorized_user_ids])
                        await channel.send(f"{developer_mentions} Main bot going offline, please renew server if needed.")
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

# Command to shut down the bot
@bot.command(name='shutdown', help="Shut down the bot.")
@commands.check(is_authorized)
async def shutdown(ctx):
    await ctx.send("Shutting down the bot...")
    logging.info(f"Shutdown command issued by {ctx.author}.")
    save_player_cards()
    await shutdown_bot()

# Handle shutdown signal
def handle_shutdown_signal(signal, frame):
    save_player_cards()  # Save player cards on shutdown
    loop = asyncio.get_event_loop()
    loop.create_task(shutdown_bot())

signal.signal(signal.SIGINT, handle_shutdown_signal)
signal.signal(signal.SIGTERM, handle_shutdown_signal)

# Ensures that it will only work when executed directly, and will log any errors to the terminal
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
