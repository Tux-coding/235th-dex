import discord # type: ignore
import random
import logging
from discord.ext import commands # type: ignore
from dotenv import load_dotenv
import os

# Configuring logging into the terminal
logging.basicConfig(level=logging.INFO)

# Loading the token from the .env file
load_dotenv()
token = os.getenv('DISCORD_TOKEN')
if not token: # If he can't find the token, error message and exit will occur
    logging.error("DISCORD_TOKEN missing!") 
    exit(1)

# Bot Configuration, this holds what character you have to use to give the bot a command (in this case "!")
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Event: When the bot is ready, it prints to the console that it's online.
@bot.event
async def on_ready():
    print(f'We have logged in as {bot.user}')
    logging.info("Logging is configured correctly.")

#gives you a random number
@bot.command(name='random_number')
async def randomNumber(ctx):
    random_number = random.randint(1, 150)
    await ctx.send(random_number)


# Command: Respond to a simple message
@bot.command(name='hello')
async def hello(ctx):
    await ctx.send('Hello! I am your Discord bot.')

#Command: basicly coded for chances of getting cards. Horribly coded, FIRST THING TO CHANGE IF IT IS DONE!!!!! 
@bot.command(name='spawn')
async def spawn(ctx):
    random_card = random.randint(1, 200) #chooses a random integer 
    logging.info(f'Generated random card number: {random_card}') # prints the integer to the console for troubleshooting purposes
    
    if  random_card <= 21:  # basicly the chance, in this instance if random choosen integer is lower than 21 then:
        await ctx.send("You caught a wild Dicer!") # it sends a message that you caught the pokemon ;)
        
        # along with the message it will send the picture
        embed = discord.Embed(title="Dicer", description="Here's your catch!")
        embed.set_image(url="https://media.discordapp.net/attachments/1322202570529177642/1322205795957342228/CC-1947_2.png?ex=6770079b&is=676eb61b&hm=1d292e779b29d2258042788a7f8e0783e881dccd821baf36d3668a9c58d6dd&=&format=webp&quality=lossless&width=479&height=671")
        await ctx.send(embed=embed)
    elif random_card >= 179 and random_card <= 190: #if the random number is higher than 179 and lower than 190 then:
        await ctx.send("You caught a wild Reyes!") # it sends a message that you caught the pokemon ;)
        embed = discord.Embed(title="Reyes", description="Here's your catch!")
        # embed.set_image(url="https://media.discordapp.net/attachments/1322202570529177642/1322205795957342228/CC-1947_2.png?ex=6770079b&is=676eb61b&hm=1d292e779b29d2258042788a7f8e0783e881dccd821baf36d3668a9c58d6dd&=&format=webp&quality=lossless&width=479&height=671") 
        await ctx.send(embed=embed)
    else:
        await ctx.send("You didn't catch anything, poor you...")

# Ensures that it will only work when executed directly, and will log any errors to the terminal
if __name__ == "__main__":
    try:
        bot.run(token)
    except Exception as e:
        logging.error(f"Error running the bot: {e}")
