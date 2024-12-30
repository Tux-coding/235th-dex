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


# Configuring logging into the terminal
logging.basicConfig(level=logging.INFO, format='%(asctime)s:%(levelname)s:%(name)s: %(message)s')

# Loading the token from the .env file
load_dotenv()
token = os.getenv('DISCORD_TOKEN')
channel_id = os.getenv('CHANNEL_ID')

# Debugging prints
logging.info(f"DISCORD_TOKEN: {token}")
logging.info(f"CHANNEL_ID: {channel_id}")

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
def load_player_cards():
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
        player_cards = {}
        logging.info("No player cards file found. Starting with an empty dictionary.")
    except json.JSONDecodeError:
        player_cards = {}
        logging.error("Error decoding JSON from player cards file. Starting with an empty dictionary.")

# Save player cards to a JSON file
def save_player_cards():
    with open('player_cards.json', 'w') as f:
        json.dump(player_cards, f)
    logging.info(f"Saved player cards: {player_cards}")

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

        if self.card_input.value.lower() == self.card_name.lower():
            user_id = str(user.id)  # Ensure user ID is a string
            if user_id not in player_cards:
                player_cards[user_id] = []
            if self.card_name not in player_cards[user_id]:  # Check for duplicates
                player_cards[user_id].append(self.card_name)
                save_player_cards()  # Save player cards after catching a card
                await interaction.response.send_message(f"{user.mention} caught the card: {self.card_name}!", ephemeral=False)

                # Mark the card as claimed
                self.view.card_claimed = True

                # Disable the button after it has been clicked
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
        if user.id in player_cards and self.card_name in player_cards[user.id]:
            await interaction.response.send_message("You already have this card!", ephemeral=True)
        else:
            modal = CatchModal(self.card_name, self.view, interaction.message)
            await interaction.response.send_modal(modal)

class CatchView(View):
    def __init__(self, card_name):
        super().__init__(timeout=None)
        self.card_claimed = False
        self.add_item(CatchButton(card_name))

# List of cards with their names and image URLs
cards = [
    {
        "name": "Dicer",
        "spawn_image_url": "https://media.discordapp.net/attachments/1322205679028670495/1322205863611600896/RobloxScreenShot20241227_145936188.png?ex=677201eb&is=6770b06b&hm=f74d9e756dd8ae25b0c65b6fbdfd169c1c08679912c956c068f75c50171e9b95&=&format=webp&quality=lossless",
        "card_image_url": "https://cdn.discordapp.com/attachments/1322202570529177642/1322205795957342228/CC-1947_2.png?ex=6773535b&is=677201db&hm=768dee2d6535855233f44910ff8dd7ca45485ca6ba81a6f36ec7f3a554bd3941&",
        "rarity": 5  # 5% chance of spawning
    },
    {
        "name": "Reyes",
        "spawn_image_url": "https://media.discordapp.net/attachments/1322205679028670495/1322503928591548482/RobloxScreenShot20241228_105546001.png?ex=67726ec3&is=67711d43&hm=4978a7aa74371952a439ec75fd2ac459bb1f49af739b8ec7d0f6d145c54642d9&=&format=webp&quality=lossless",
        "card_image_url":"https://cdn.discordapp.com/attachments/1322202570529177642/1322585956938944512/CC-1598_Reyes_is_the_Marshal_Commander_of_the_235th_Elite_Corps.png?ex=677363e8&is=67721268&hm=35ffd80d26b26c28e60db3da255a071919fa7f0e87c1d8e2aecdd75e65e5031b&",
        "rarity": 0.5
    },
    {
        "name": "Sentinel",
        "spawn_image_url": "https://media.discordapp.net/attachments/1322205679028670495/1322284693164523520/RobloxScreenShot20241227_202621517.png?ex=67724b55&is=6770f9d5&hm=79e9f8374ffa7b0138f938a11d7916b45ee79b2afdf1fc6c8197c27349b46684&=&format=webp&quality=lossless&width=377&height=350",
        "card_image_url": "https://media.discordapp.net/attachments/1322202570529177642/1323317997414121665/Just_another_trooper_trying_to_stay_alive._He_doesnt_like_insurgents._His_left_arm_and_left_eye_are_gone_due_to_the_Gulag.png?ex=6774136c&is=6772c1ec&hm=f4d4550607203a12eaa72d7b6a0086efb64bf3d8c623650d713dbf7a96bc242d&=&format=webp&quality=lossless&width=479&height=671",
        "rarity": 23  
    },
    {
        "name": "Blau",
        "spawn_image_url": "https://media.discordapp.net/attachments/1322205679028670495/1322289394404687957/RobloxScreenShot20241227_204520218.png?ex=67724fb6&is=6770fe36&hm=b3fc9388163dfb8f6d33ea520cccc373156a6ea8c5b558d370d388a8ec8ae7d8&=&format=webp&quality=lossless&width=396&height=350",
        "card_image_url": "https://cdn.discordapp.com/attachments/1322202570529177642/1322289134630600724/CT-_Blau.png?ex=6773a0f8&is=67724f78&hm=29349d7e624fcb150f298c40b15d68575d5bee22dace451856ea9da23e43db58&",
        "rarity": 12.5 
    },
    {
        "name": "Hounder",
        "spawn_image_url": "https://media.discordapp.net/attachments/1322205679028670495/1322295423360176218/RobloxScreenShot20241227_210852940.png?ex=67725553&is=677103d3&hm=c32cad3bc0dc2ebc26cbdfeba7e8fb5ea83b55e557eafbfc3a0358a760654d7e&=&format=webp&quality=lossless",
        "card_image_url": "https://cdn.discordapp.com/attachments/1322202570529177642/1322293233815912498/CT-_Blau_1.png?ex=6773a4c9&is=67725349&hm=e37704c3fa30bc469f1b20c7bd7e18e25abe8c1d6bc06b1cbcd3b85d359d2c10&",
        "rarity": 9.5  
    },
    {
        "name": "Pipopro",
        "spawn_image_url": "https://media.discordapp.net/attachments/1322205679028670495/1322977622778576976/artworks-OF3WFPHsapfnZrW8-lDiZAQ-t500x500.png?ex=67737f2d&is=67722dad&hm=1ec22c5b9af4c994af583de216afe05660c777e5437a738750577b9a49cbdf90&=&format=webp&quality=lossless",
        "card_image_url": "https://cdn.discordapp.com/attachments/1322202570529177642/1322977702105579591/Pipopro.png?ex=67737f3f&is=67722dbf&hm=2cc3c639f2e613963f78ec6dbfc274df6f6a74666d06461e4bfb60fdb5c3568d&",
        "rarity": 0.75 
    },
    {
        "name": "Wilson",
        "spawn_image_url": "https://media.discordapp.net/attachments/1322205679028670495/1323344360879689730/RobloxScreenShot20241230_161947936.png?ex=67742bfa&is=6772da7a&hm=14a472045ae47f536705b91cb91bdae7ea52674d1cde2799ad65835c0c85d8df&=&format=webp&quality=lossless&width=532&height=350",
        "card_image_url": "https://media.discordapp.net/attachments/1322202570529177642/1323314295286665246/CC-.png?ex=67740ff9&is=6772be79&hm=54193da49212bd838fb47e993c16c2af1da3987a04373fc1a20def924f0744a6&=&format=webp&quality=lossless&width=479&height=671",
        "rarity": 1 
    }
]

# Part that does rarity
def weighted_random_choice(cards):
    total = sum(card['rarity'] for card in cards)
    r = random.uniform(0, total)
    upto = 0
    for card in cards:
        if upto + card['rarity'] >= r:
            return card
        upto += card['rarity']
    return None

# Part that holds the timer and the channel where the card spawns
@tasks.loop(minutes=1)
async def spawn_card():
    try:
        channel = bot.get_channel(int(channel_id)) # channel_id is the channel where the card will spawn
        if channel:
            card = weighted_random_choice(cards)
            logging.info(f"Selected card: {card['name']}")
            embed = discord.Embed(title=f"A wild card has appeared!", description="Click the button below to catch it!")
            embed.set_image(url=card['spawn_image_url'])
            await channel.send(embed=embed, view=CatchView(card['name']))
        else:
            logging.error(f"Channel not found: {channel_id}")
    except Exception as e:
        logging.error(f"An error occurred: {e}")

# If error, he says why
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        await ctx.send("Command not found.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Missing arguments.")
    else:
        await ctx.send("An error occurred.")

# When the bot is ready, it prints to the console that it's online
@bot.event
async def on_ready():
    load_player_cards()  # Load player cards when the bot starts
    print(f'We have logged in as {bot.user}')
    logging.info("Logging is configured correctly.")
    spawn_card.start()

# Gives a random number between 0 and 10000000
@bot.command(name='random_number')
async def random_number(ctx):
    random_number = random.randint(0, 10000000)
    await ctx.send(f'Your random number is: {random_number}')

# Respond to a simple message
@bot.command(name='hello')
async def hello(ctx):
    await ctx.send('Hello! I am your Discord bot.')


# Command that hopefully sees your cards
@bot.command(name='mycards')
async def my_cards(ctx):
    user_id = str(ctx.author.id)  # Ensure user ID is a string
    logging.info(f'User ID: {user_id}')
    logging.info(f'Player cards: {player_cards}')
    if user_id in player_cards:
        cards = player_cards[user_id]
        logging.info(f"User {user_id} has cards: {cards}")
        await ctx.send(f"You have caught: {', '.join(cards)}")
    else:
        logging.info(f"User {user_id} has no cards.")
        await ctx.send("You haven't caught any cards yet.")

# see_card command to see a specific card
@bot.command(name='see_card')
async def see_card(ctx):
    user_id = str(ctx.author.id)  # Ensure user ID is a string
    logging.info(f'User ID: {user_id}')
    logging.info(f'Player cards: {player_cards}')
    
    if user_id in player_cards and player_cards[user_id]:
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
    if user_id in player_cards:
        user_cards = player_cards[user_id]
        num_user_cards = len(user_cards)
        percentage = (num_user_cards / total_cards) * 100
        card_list = "\n".join(user_cards)
        await ctx.send(f"You have caught {num_user_cards} out of {total_cards} cards ({percentage:.2f}%).\n\nYour cards:\n{card_list}")
    else:
        await ctx.send(f"You haven't caught any cards yet. There are {total_cards} cards available.")

# Command to spawn a certain card, restricted to a specific user
@bot.command(name='spawn_card')
async def spawn_card_command(ctx, card_name: str):
    specific_user_id = '573878397952851988'
    if str(ctx.author.id) != specific_user_id:
        await ctx.send("You do not have permission to use this command.")
        return

    card = next((card for card in cards if card["name"].lower() == card_name.lower()), None)
    if card:
        channel = bot.get_channel(int(channel_id))
        if channel:
            embed = discord.Embed(title=f"A wild {card['name']} has appeared!", description="Click the button below to catch it!")
            embed.set_image(url=card['spawn_image_url'])
            await channel.send(embed=embed, view=CatchView(card['name']))
            await ctx.send(f"{card['name']} has been spawned.")
        else:
            await ctx.send("Channel not found.")
    else:
        await ctx.send("Card not found.")

# When the bot disconnects, it will send a message to the channel
@bot.event
async def on_disconnect():
    channel = bot.get_channel(int(channel_id))
    if channel:
        await channel.send("235th dex going offline")
    logging.info("235th dex going offline")

# Handle shutdown signal
def handle_shutdown_signal(signal, frame):
    save_player_cards()  # Save player cards on shutdown
    loop = asyncio.get_event_loop()
    loop.create_task(bot.close())

# Register signal handlers for graceful shutdown
signal.signal(signal.SIGINT, handle_shutdown_signal)
signal.signal(signal.SIGTERM, handle_shutdown_signal)

# Ensures that it will only work when executed directly, and will log any errors to the terminal
if __name__ == "__main__":
    try:
        bot.run(token)
        logging.info(f'Logged in as {bot.user.name}')
    except Exception as e:
        logging.error(f'Error: {e}')