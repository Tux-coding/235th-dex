import discord
import random
from discord.ext import commands

# Bot Configuration
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Event: When the bot is ready
@bot.event
async def on_ready():
    print(f'We have logged in as {bot.user}')

@bot.command()
async def randomNumber(ctx):
    random_number = random.randint(1, 150)
    await ctx.send(random_number)


# Command: Respond to a simple message
@bot.command()
async def hello(ctx):
    print("fucking mandalorian")
    await ctx.send('Hello! I am your Discord bot.')

@bot.command()
async def gimmeBalls(ctx):
    embed = discord.Embed(title="Here is an image!")  # Customize the embed
    embed.set_image(url="https://media.discordapp.net/attachments/1112053925055570071/1321780520761425920/DF6857D8-849E-4FBA-A47E-B6F76DBDAACB.jpg?ex=676e7b89&is=676d2a09&hm=8c8722eb90557679a2052b55a93356b790dc656b678acebe43ee185ccfdd29f9&=&format=webp&width=644&height=671")  # Replace with your image URL
    await ctx.send(embed=embed)


# Run the bot
bot.run('MTMyMTgxMzI1NDEyODkzMDg2Nw.GsJv7A.w_qdot6QcMKGPBPe65_1dycFQfxKZ9up7-uyBw')
