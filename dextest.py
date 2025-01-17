import random
import logging
import os
import asyncio
import signal
import json

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

# Player cards view starter
player_cards = {}

# Load player cards from a JSON file
def load_player_cards() -> None:
    global player_cards
    try:
        if os.path.getsize('player_cards.json') > 0:  # Check if the file is not empty
            with open('player_cards.json', 'r') as f:
                player_cards = json.load(f)
            # Ensure all keys are strings
            player_cards = {str(k): v for k, v in player_cards.items()}
            logging.info(f"Loaded player cards: {player_cards}")
        else:
            player_cards = {}
            logging.info("Player cards file is empty. Starting with an empty dictionary.")
    except FileNotFoundError:
        logging.error("No player cards file found. Aborting.")
        exit(1)
    except json.JSONDecodeError:
        logging.error("Error decoding JSON from player cards file. Aborting.")
        exit(1)

# Save player cards to a JSON file
def save_player_cards() -> None:
    with open('player_cards.json', 'w') as f:
        json.dump(player_cards, f)
    logging.info(f"Saved player cards: {player_cards}")

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
        user = interaction.user
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

def is_authorized(ctx):
    return str(ctx.author.id) in authorized_user_ids

# Command to change the spawn mode
@bot.command(name='set_spawn_mode')
@commands.check(is_authorized)
async def set_spawn_mode(ctx, mode: str):
    global spawn_mode
    mode = mode.lower()
    if mode in ['both', 'test', 'none']:
        spawn_mode = mode
        await ctx.send(f"Spawn mode set to {spawn_mode}.")
        logging.info(f"Spawn mode changed to {spawn_mode} by {ctx.author}.")
    else:
        await ctx.send("Invalid mode. Please choose from 'both', 'test', or 'none'.")

# Part that holds the timer and the channel where the card spawns
last_spawned_card = None
spawned_messages = []

@tasks.loop(minutes=2)
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
@bot.command(name='print_stats')
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
    elif isinstance(error, commands.CheckFailure):
        await ctx.send("You do not have permission to use this command.")
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
                await channel.send("235th dex is online! Type !list_commands to see the available commands.")
                logging.info(f"Sent online message to channel {channel.id}")
            except Exception as e:
                logging.error(f"Failed to send message to channel {channel.id}: {e}")
        else:
            
            logging.error(f"Channel not found.")
    
    # Disable buttons of previous cards on restart
    for message in spawned_messages:
        view = message.components[0]
        for item in view.children:
            if isinstance(item, Button):
                item.disabled = True
        await message.edit(view=view)
    spawned_messages = []

    spawn_card.start()


# see_card command to see a specific card
@bot.command(name='see_card')
async def see_card(ctx, *, card_name: str = None):
    user_id = str(ctx.author.id)  # Ensure user ID is a string
    logging.info(f'User ID: {user_id}')
    logging.info(f'Player cards: {player_cards}')
    
    if user_id in player_cards and player_cards[user_id]:
        if card_name:
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
            options = [discord.SelectOption(label=card, value=card) for card in player_cards[user_id]]
            select = Select(placeholder="Choose a card to see", options=options)

            async def select_callback(interaction):
                if interaction.user.id != ctx.author.id:
                    await interaction.response.send_message("You can only view your own cards.", ephemeral=True)
                    return
                selected_card_name = select.values[0]
                selected_card = next(card for card in cards if card["name"] == selected_card_name)
                embed = discord.Embed(title=f"Here's your {selected_card_name}", description="")
                embed.set_image(url=selected_card["card_image_url"])
                await interaction.response.send_message(embed=embed)

            select.callback = select_callback
            view = View()
            view.add_item(select)
            await ctx.send("Select a card to see", view=view)
    else:
        await ctx.send("You haven't caught any cards yet.")

# Command that shows the user's progress
@bot.command(name='progress')
async def progress(ctx):
    user_id = str(ctx.author.id)  # Ensure user ID is a string
    logging.info(f'User ID: {user_id}')
    logging.info(f'Player cards: {player_cards}')
    
    total_cards = len(cards)
    if user_id in player_cards and player_cards[user_id]:
        user_cards = player_cards[user_id]
        num_user_cards = len(user_cards)
        percentage = (num_user_cards / total_cards) * 100
        user_cards_list = '\n'.join(sorted(user_cards))
        await ctx.send(f"You have caught {num_user_cards} out of {total_cards} cards ({percentage:.2f}%).\n\nYour cards:\n{user_cards_list}")
    else:
        await ctx.send(f"You haven't caught any cards yet. There are {total_cards} cards available.")

# Command to spawn a certain card, restricted to a specific user
@bot.command(name='spawn_card')
@commands.check(is_authorized)
async def spawn_card_command(ctx, card_name: str):
    card_name = card_name.strip().lower()
    if not all(c.isalnum() or c.isspace() or c in ["'", "-"] for c in card_name):
        await ctx.send("Invalid card name. Only alphanumeric characters, spaces, apostrophes, and hyphens are allowed.")
        return

    card = next((card for card in cards if card_name == card["name"].lower() or card_name in [alias.lower() for alias in card.get("aliases", [])]), None)
    if card:
        channel = bot.get_channel(int(channel_id))
        if channel:
            embed = discord.Embed(title=f"A wild card has appeared!", description="Click the button below to catch it!")
            embed.set_image(url=card['spawn_image_url'])
            await channel.send(embed=embed, view=CatchView(card['name']))
            await ctx.send(f"{card['name']} has been spawned.")
        else:
            await ctx.send("Channel not found.")
    else:
        await ctx.send("Card not found.")

#///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
#other commands not related to the card game
#///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////

# Respond to a simple message
@bot.command(name='hello')
async def hello(ctx):
    await ctx.send('Hello! I am the 235th dex! At your service!')

# Gives a random number between 0 and 10000000
@bot.command(name='random_number')
async def random_number(ctx):
    random_number = random.randint(0, 10000000)
    await ctx.send(f'Your random number is: {random_number}')


# command to show the current commands that users can use
@bot.command(name='list_commands')
async def list_commands(ctx):
    commands_list = [
        '!hello - Responds with a greeting message.',
        '!random_number - Gives a random number',
        '!info - Shows the current release ',
        '!see_card - View a card you have caught.',
        '!progress - Shows your progress in catching cards.',
        '!print_stats - Shows the stats of a certain card.',
    ]
    commands_description = '\n'.join(commands_list)
    await ctx.send(f'Here is a list of all the commands you can use:\n{commands_description}')

#info, command to show the current release
@bot.command(name='info')
async def info(ctx):
    await ctx.send('Current release: v.1.0.0') #expand later when we actually released the bot to the public

# Command to play a certain GIF, restricted to authorized users
@bot.command(name='celebrate')
@commands.check(is_authorized)
async def play_gif(ctx):
    gif_url = "https://images-ext-1.discordapp.net/external/g2WvOwPwXD3KtaqKdjNQ-RWFBmwpS01Nc2f_NPURW7w/https/media.tenor.com/BDxIoo-dxPgAAAPo/missouri-tigers-truman-the-tiger.mp4"
    await ctx.send(gif_url)


#///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
#other cool things for shutdown and signal handling
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
    await bot.close()

# Command to shut down the bot
@bot.command(name='shutdown')
@commands.check(is_authorized)
async def shutdown(ctx):
    await ctx.send("Shutting down the bot...")
    logging.info(f"Shutdown command issued by {ctx.author}.")
    save_player_cards()  # Save player cards on shutdown
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
