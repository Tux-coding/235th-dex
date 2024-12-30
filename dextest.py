import discord # type: ignore
import random
import logging
from discord.ext import commands, tasks # type: ignore
from discord.ui import Button, View #type:ignore 
from dotenv import load_dotenv # type: ignore //please ensure that you have python-dotenv installed (command is "pip install python-dotenv")
import os

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

# Button that hopefully does the button work
class CatchButton(Button):
    def __init__(self, card_name):
        super().__init__(label="Catch the card", style=discord.ButtonStyle.primary)
        self.card_name = card_name

    async def callback(self, interaction: discord.Interaction):
        user = interaction.user
        if user.id not in player_cards:
            player_cards[user.id] = []
        player_cards[user.id].append(self.card_name)
        await interaction.response.send_message(f"{user.mention} caught the card: {self.card_name}!", ephemeral=True)

        # Disable the button after it has been clicked
        self.disabled = True
        await interaction.message.edit(view=self.view)

# Same as above
class CatchView(View):
    def __init__(self, card_name):
        super().__init__(timeout=None)
        self.add_item(CatchButton(card_name))

# List of cards with their names and image URLs
cards = [
    {
        "name": "Dicer",
        "spawn_image_url": "https://media.discordapp.net/attachments/1322205679028670495/1322205863611600896/RobloxScreenShot20241227_145936188.png?ex=677201eb&is=6770b06b&hm=f74d9e756dd8ae25b0c65b6fbdfd169c1c08679912c956c068f75c50171e9b95&=&format=webp&quality=lossless",
        "card_image url": "https://cdn.discordapp.com/attachments/1322202570529177642/1322205795957342228/CC-1947_2.png?ex=6773535b&is=677201db&hm=768dee2d6535855233f44910ff8dd7ca45485ca6ba81a6f36ec7f3a554bd3941&",
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
        "card_image_url": "https://cdn.discordapp.com/attachments/1322202570529177642/1322289085183955004/CT-_1.png?ex=6773a0ec&is=67724f6c&hm=32aef299a210aadcc169dbe3867b9a44a64b1d23d44e7af430d47e3a8a2e583e&",
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
@tasks.loop(minutes=10)
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

#@bot.command(name = "see_card") it does not work,
#async def see_card(ctx):
 #   embed = discord.Embed(title = "this is your card!")
  #  embed.set_image(url=cards["card_image_url"])
   # await ctx.send(embed=embed)


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
    user_id = ctx.author.id
    logging.info(f'User ID: {user_id}')
    logging.info(f'Player cards: {player_cards}')
    if user_id in player_cards:
        cards = player_cards[user_id]
        await ctx.send(f"You have caught: {', '.join(cards)}")
    else:
        await ctx.send("You haven't caught any cards yet.")

# Ensures that it will only work when executed directly, and will log any errors to the terminal
if __name__ == "__main__":
    try:
        bot.run(token)
        logging.info(f'Logged in as {bot.user.name}')
    except Exception as e:
        logging.error(f'Error: {e}')