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
        "image_url": "https://media.discordapp.net/attachments/1322205679028670495/1322205863611600896/RobloxScreenShot20241227_145936188.png?ex=677201eb&is=6770b06b&hm=f74d9e756dd8ae25b0c65b6fbdfd169c1c08679912c956c068f75c50171e9b95&=&format=webp&quality=lossless"
    },
    {
        "name": "Reyes",
        "image_url": "https://media.discordapp.net/attachments/1322205679028670495/1322503928591548482/RobloxScreenShot20241228_105546001.png?ex=67726ec3&is=67711d43&hm=4978a7aa74371952a439ec75fd2ac459bb1f49af739b8ec7d0f6d145c54642d9&=&format=webp&quality=lossless"
    }
]
# Part that holds the timer and the channel where the card spawns
@tasks.loop(minutes=10)
async def spawn_card():
    try:
        channel = bot.get_channel(int(channel_id))
        if channel:
            card = random.choice(cards)
            logging.info(f"Selected card: {card['name']}")
            embed = discord.Embed(title=f"A wild 235th clone has appeared!", description="Click the button below to catch it!")
            embed.set_image(url=card['image_url'])
            await channel.send(embed=embed, view=CatchView())
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

#Command: basicly coded for chances of getting cards. Horribly coded, FIRST THING TO CHANGE IF IT IS DONE!!!!! 
@bot.command(name='spawn')
async def spawn(ctx):
    random_card = random.randint(1, 200) #chooses a random integer 
    logging.info(f'Generated random card number: {random_card}') # prints the integer to the console for troubleshooting purposes
    
    user_id = ctx.author.id
    if user_id not in player_cards:
        player_cards[user_id] = []
    
    if  random_card <= 21:  # basicly the chance, in this instance if random choosen integer is lower than 21 then:
        embed = discord.Embed(title = "Dicer", description ="Who is this?")      
        embed.set_image(url="https://media.discordapp.net/attachments/1322205679028670495/1322205863611600896/RobloxScreenShot20241227_145936188.png?ex=6771592b&is=677007ab&hm=dce13f31e721d625b43ac537d5d17b8e3dc5158d67a9035f59b5d4971bfe8502&=&format=webp&quality=lossless&width=650&height=667")
        await ctx.send(embed=embed)
        
        await ctx.send("You caught a wild Dicer!") # it sends a message that you caught the guy
        
        # along with the message it will send the picture
        embed = discord.Embed(title="Dicer", description="Here's your catch!")
        embed.set_image(url="https://media.discordapp.net/attachments/1322202570529177642/1322205795957342228/CC-1947_2.png?ex=6770079b&is=676eb61b&hm=1d292e779b29d2258042788a7f8e0783e881dccd821baf36d3668a9c58d6dd&=&format=webp&quality=lossless&width=479&height=671")
        await ctx.send(embed=embed)

        player_cards[user_id].append("Dicer") # adds the card to the player's collection

    elif random_card == 200: # If the random number is 200:
        await ctx.send("You caught a wild Reyes!") 

        embed = discord.Embed(title="Reyes", description="Here's your catch!")
        embed.set_image(url="https://media.discordapp.net/attachments/1321821231850328068/1322584515146678335/CC-1598_Reyes_is_the_Marshal_Commander_of_the_235th_Elite_Corps._He_has_led_the_Corps_since_the_very_beginning_although_the_highest_rank_was_Senior_Commander_back_in_the_day._Known_for_his_steady.png?ex=67716850&is=677016d0&hm=c9811709d3f40e4f08220a9e1f553eeac4e89b32608473a88df31e646b6450a5&=&format=webp&quality=lossless&width=479&height=671") 
        await ctx.send(embed=embed)

        player_cards[user_id].append("Reyes")
    else:
        await ctx.send("You didn't catch anything, poor you...")

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