import random
import logging
import os
import asyncio
import signal
import json
import datetime
import shutil

from typing import List
from collections import Counter

import discord # type: ignore
from discord.ext import commands, tasks # type: ignore
from discord.ui import Button, View, Select, Modal, TextInput #type:ignore 
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

# Player cards view starter
player_cards = {}

# Lock to ensure only one user can submit at a time
modal_lock = asyncio.Lock()

# Load player cards from a JSON file
def load_player_cards() -> None:
    global player_cards
    try:
        if os.path.exists('player_cards.json') and os.path.getsize('player_cards.json') > 0:
            with open('player_cards.json', 'r') as f:
                player_cards = json.load(f)
            # Ensure all keys are strings
            player_cards = {str(k): v for k, v in player_cards.items()}
        else:
            # Create a new file if it doesn't exist or is empty
            player_cards = {}
            logging.info("Player cards file is empty or doesn't exist. Creating a new file.")
            save_player_cards()  # Save the empty dictionary to create the file
    except json.JSONDecodeError as e:
        logging.error(f"Error decoding JSON from player cards file: {e}")
        # Try to recover from the most recent backup
        backup_files = [f for f in os.listdir() if f.startswith("player_cards_backup_")]
        if backup_files:
            latest_backup = max(backup_files)
            logging.info(f"Attempting to recover from backup: {latest_backup}")
            try:
                with open(latest_backup, 'r') as f:
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
    try:
        with open('player_cards.json', 'w') as f:
            json.dump(player_cards, f, indent=4)
    except Exception as e:
        logging.error(f"Error saving player cards: {e}")

# Backup creation
backup_folder = "backup_folder"
os.makedirs(backup_folder, exist_ok=True)

def create_backup():
    try:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"player_cards_backup_{timestamp}.json"
        backup_filepath = os.path.join(backup_folder, backup_filename)
        shutil.copy('player_cards.json', backup_filepath)
        logging.info(f"Created backup: {backup_filename} in {backup_filepath}")
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
        global modal_lock
        user = interaction.user

        # Attempt to acquire the lock
        if modal_lock.locked():
            await interaction.response.send_message("The card is currently being claimed by another user. Please wait.", ephemeral=True)
            return
        
        async with modal_lock:
            if self.view.card_claimed:
                await interaction.response.send_message("The card has already been claimed.", ephemeral=True)
                return

            input_name = self.card_input.value.lower()
            if input_name == self.card_name.lower() or input_name in [alias.lower() for alias in next(card['aliases'] for card in cards if card['name'].lower() == self.card_name.lower())]:
                user_id = str(user.id)
                if not user_has_card(user_id, self.card_name):
                    player_cards.setdefault(user_id, []).append(self.card_name)
                    save_player_cards()
                    await interaction.response.send_message(f"{user.mention} caught the card: {self.card_name}!", ephemeral=False)
                    self.view.card_claimed = True
                    for item in self.view.children:
                        if isinstance(item, Button):
                            item.disabled = True
                    await self.message.edit(view=self.view)
                else:
                    await interaction.response.send_message(f"{user.mention}, you already have this card.", ephemeral=True)
            else:
                await interaction.response.send_message(f"{user.mention}; Incorrect name.", ephemeral=False)

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
        if user_has_card(str(user.id), self.card_name):
            await interaction.response.send_message("You already have this card!", ephemeral=True)
        else:
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
        self.missing_cards = missing_cards
        self.user = user
        self.current_page = 0
        self.viewing_owned = True  # Start by viewing owned cards
        
        # Calculate pages needed for owned cards
        self.owned_pages = max(1, (len(user_cards) + 9) // 10)  # At least 1 page
        
        # Calculate pages needed for missing cards
        self.missing_pages = max(1, (len(missing_cards) + 9) // 10)  # At least 1 page
        
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
            description=f"Showing your owned cards ({len(self.user_cards)}/{len(self.user_cards) + len(self.missing_cards)} collected)",
            color=discord.Color.green()
        )
        
        start = self.current_page * 10
        end = min(start + 10, len(self.user_cards))
        
        if self.user_cards:
            owned_cards = "\n".join([f"• {card}" for card in self.user_cards[start:end]])
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
            view = View.from_message(message)
            for item in view.children:
                if isinstance(item, Button):
                    item.disabled = True
            await message.edit(view=view)
        spawned_messages = []

        if spawn_mode in ['both', 'test']:
            test_channel = bot.get_channel(int(test_channel_id))
            if test_channel:
                channels.append(test_channel)
            else:
                logging.error("Test channel not found.")
        
        if spawn_mode == 'both':
            main_channel = bot.get_channel(int(channel_id))
            if main_channel:
                channels.append(main_channel)
            else:
                logging.error("Main channel not found.")
        
        if not channels:
            logging.info("No channels configured for spawning cards.")
            return

        card = weighted_random_choice(cards)
        while card == last_spawned_card:
            card = weighted_random_choice(cards)
        
        last_spawned_card = card
        logging.info(f"Selected card: {card['name']}")
        embed = discord.Embed(title=f"A wild card has appeared!", description="Click the button below to catch it!")
        embed.set_image(url=card['spawn_image_url'])
        
        for channel in channels:
            msg = await channel.send(embed=embed, view=CatchView(card['name']), allowed_mentions=discord.AllowedMentions.none())
            spawned_messages.append(msg)
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        for channel in channels:
            await channel.send("An error occurred while spawning a card.")

# Command to print the stats of a card
@bot.command(name='stats', help="Show the stats of a specific card.")
async def print_stats(ctx, *, card_name: str):
    card = next((card for card in cards if card_name.lower() == card["name"].lower() or card_name in [alias.lower() for alias in card.get("aliases", [])]), None)
    if card:
        embed = discord.Embed(title=f"Stats for {card['name']}", description="")
        embed.add_field(name="Health", value=card["health"], inline=True)
        embed.add_field(name="Damage", value=card["damage"], inline=True)
        embed.add_field(name="Rarity", value=f"{card['rarity']}%", inline=True)
        await ctx.send(embed=embed)
    else:
        await ctx.send("Card not found.")

# If error, he says why
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        await ctx.send("Command not found.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Missing arguments.")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("Bad argument.")
    elif isinstance(error, commands.DisabledCommand):
        await ctx.send("This command is disabled.")
    elif isinstance(error, commands.CommandInvokeError):
        logging.error(f"An error occurred while invoking the command: {error}")
        await ctx.send("An error occurred while invoking the command.")
    elif isinstance(error, commands.TooManyArguments):
        await ctx.send("Too many arguments provided.")
    elif isinstance(error, commands.CheckFailure):
        if not (is_test_mode and str(ctx.author.id) not in authorized_user_ids):
            await ctx.send("You do not have permission to use this command.")
    elif isinstance(error, commands.UserInputError):
        await ctx.send("There was an error with your input.")
    else:
        logging.error(f"An error occurred: {error}")
        await ctx.send("An error occurred.")

# When the bot is ready, it prints to the console that it's online
@bot.event
async def on_ready():
    global spawned_messages
    load_player_cards()  # Load player cards when the bot starts
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

@bot.command(name='give')
async def give_card(ctx, card: str, receiving_user: discord.Member):
    sender_id = str(ctx.author.id)
    receiver_id = str(receiving_user.id)
    card_lower = card.lower()
    
    sender_cards = player_cards.get(sender_id, [])
    if card_lower not in map(str.lower, sender_cards):
        await ctx.send(f"You don't own the card `{card}`.")
        return
    
    # Remove the card from the sender's inventory
    actual_card_name = next(c for c in sender_cards if c.lower() == card_lower)
    sender_cards.remove(actual_card_name)

    # Add the card to the receiver's inventory
    receiver_cards = player_cards.setdefault(receiver_id, [])
    receiver_cards.append(actual_card_name)

    save_player_cards()  # Save the updated player cards
    await ctx.send(f"{ctx.author.mention} has given `{actual_card_name}` to {receiving_user.mention}.")
    logging.info(f"{ctx.author} gave {actual_card_name} to {receiving_user}.")

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


# command to show the current commands that users can use
@bot.command(name='commands_dex', help="Shows a list of all the commands you can use.")
async def list_commands(ctx):
    commands_list = [
        '!hello - Responds with a greeting message.',
        '!random_number - Gives a random number',
        '!info_dex - Shows the current release ',
        '!see_card - View a card you have caught.',
        '!progress - Shows your progress in catching cards.',
        '!stats - Shows the stats of a certain card.',
        '!give - Give a card to another user.',
        '!stats_full - Gives stats of the bot.',
        'If you have any questions about the bot or commands, please go to https://discordapp.com/channels/1103817592889679892/1323370905874989100'
    ]
    commands_description = '\n'.join(commands_list)
    await ctx.send(f'Here is a list of all the commands you can use:\n{commands_description}')

#info, command to show the current release
@bot.command(name='info_dex', help="General info about the dex")
async def info(ctx):

    #bit of code to count the lines of code in the project
    project_dir = '/home/container'
    total_lines = 0

    for root, _, files in os.walk(project_dir):
        for file in files:
            if file.endswith('test.py') or file.endswith('cards.py'):
                file_path = os.path.join(root, file)
                with open(file_path, 'r') as f:
                    total_lines += sum(1 for _ in f)
                    
    embed = discord.Embed(title="Current Release", description=f"v.1.2.5, \"The more-stats update\"\n Developers: <@1035607651985403965>, <@573878397952851988> and <@845973389415284746> \n Total lines of code: {total_lines}")
    await ctx.send(embed=embed) #expand later when we actually released the bot to the public

# Command to play a certain GIF, restricted to authorized users
@bot.command(name='celebrate')
@commands.check(is_authorized)
async def play_gif(ctx):
    gif_url = "https://images-ext-1.discordapp.net/external/g2WvOwPwXD3KtaqKdjNQ-RWFBmwpS01Nc2f_NPURW7w/https/media.tenor.com/BDxIoo-dxPgAAAPo/missouri-tigers-truman-the-tiger.mp4"
    await ctx.send(gif_url)

# Public !stats command
@bot.command(name='stats_full', help="Show general statistics about the card game.")
async def public_stats(ctx):
    total_users = len(player_cards)
    total_cards_collected = sum(len(cards) for user_id, cards in player_cards.items() if user_id not in authorized_user_ids)
    
    # Top Collectors
    collectors = [(user_id, len(cards)) for user_id, cards in player_cards.items() if user_id not in authorized_user_ids]
    top_collectors = sorted(collectors, key=lambda x: x[1], reverse=True)[:5]
    
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
    embed.add_field(name="Most Collected Card", value=most_collected_card, inline=False)
    embed.add_field(name="Rarest Card Owned", value=rarest_card_owned, inline=False)
    
    await ctx.send(embed=embed)
#///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
#other cool things for shutdown and signal handling

@bot.before_invoke
async def check_conditions(ctx):
    if is_test_mode and str(ctx.author.id) not in authorized_user_ids and not ctx.command.name == 'set_spawn_mode':
        await ctx.send("We are currently updating the bot, please wait until we are finished.")
        raise commands.CheckFailure("Bot is in test mode.")
    if BlacklistManager.is_blacklisted(str(ctx.author.id)) and str(ctx.author.id) not in authorized_user_ids:
        await ctx.send("You are blacklisted and cannot use this bot.")
        raise commands.CheckFailure("User is blacklisted.")

# Custom shutdown function
async def shutdown_bot():
    channels = [bot.get_channel(int(channel_id)), bot.get_channel(int(test_channel_id))]
    logging.info(f"Attempting to send disconnect message to channels: {channel_id}, {test_channel_id}")
    for channel in channels:
        if channel:
            try:
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
    try:
        bot.run(token)
        logging.info(f'Logged in as {bot.user.name}')
    except Exception as e:
        logging.error(f'Error: {e}')