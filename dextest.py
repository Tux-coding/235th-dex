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
        player_cards = {}
        logging.info("No player cards file found. Starting with an empty dictionary.")
    except json.JSONDecodeError:
        player_cards = {}
        logging.error("Error decoding JSON from player cards file. Starting with an empty dictionary.")

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

# List of cards with their names and image URLs
cards = [
    {
        "name": "Dicer",
        "spawn_image_url": "https://media.discordapp.net/attachments/1322205679028670495/1322205863611600896/RobloxScreenShot20241227_145936188.png?ex=677201eb&is=6770b06b&hm=f74d9e756dd8ae25b0c65b6fbdfd169c1c08679912c956c068f75c50171e9b95&=&format=webp&quality=lossless",
        "card_image_url": "https://cdn.discordapp.com/attachments/1322202570529177642/1322205795957342228/CC-1947_2.png?ex=6773535b&is=677201db&hm=768dee2d6535855233f44910ff8dd7ca45485ca6ba81a6f36ec7f3a554bd3941&",
        "rarity": 5,  # 5% chance of spawning
        "health": 6500,
        "damage": 3500,
    },
    {
        "name": "Reyes",
        "spawn_image_url": "https://media.discordapp.net/attachments/1322205679028670495/1322503928591548482/RobloxScreenShot20241228_105546001.png?ex=67726ec3&is=67711d43&hm=4978a7aa74371952a439ec75fd2ac459bb1f49af739b8ec7d0f6d145c54642d9&=&format=webp&quality=lossless",
        "card_image_url":"https://cdn.discordapp.com/attachments/1322202570529177642/1322585956938944512/CC-1598_Reyes_is_the_Marshal_Commander_of_the_235th_Elite_Corps.png?ex=677363e8&is=67721268&hm=35ffd80d26b26c28e60db3da255a071919fa7f0e87c1d8e2aecdd75e65e5031b&",
        "rarity": 0.5,
        "health": 10000,
        "damage": 5000,
    },
    {
        "name": "Sentinel",
        "spawn_image_url": "https://media.discordapp.net/attachments/1322205679028670495/1322284693164523520/RobloxScreenShot20241227_202621517.png?ex=67724b55&is=6770f9d5&hm=79e9f8374ffa7b0138f938a11d7916b45ee79b2afdf1fc6c8197c27349b46684&=&format=webp&quality=lossless&width=377&height=350",
        "card_image_url": "https://media.discordapp.net/attachments/1322202570529177642/1323317997414121665/Just_another_trooper_trying_to_stay_alive._He_doesnt_like_insurgents._His_left_arm_and_left_eye_are_gone_due_to_the_Gulag.png?ex=6774136c&is=6772c1ec&hm=f4d4550607203a12eaa72d7b6a0086efb64bf3d8c623650d713dbf7a96bc242d&=&format=webp&quality=lossless&width=479&height=671",
        "rarity": 23,
        "health": 1650,
        "damage": 550,
    },
    {
        "name": "Blau",
        "spawn_image_url": "https://media.discordapp.net/attachments/1322205679028670495/1322289394404687957/RobloxScreenShot20241227_204520218.png?ex=67724fb6&is=6770fe36&hm=b3fc9388163dfb8f6d33ea520cccc373156a6ea8c5b558d370d388a8ec8ae7d8&=&format=webp&quality=lossless&width=396&height=350",
        "card_image_url": "https://cdn.discordapp.com/attachments/1322202570529177642/1322289134630600724/CT-_Blau.png?ex=6773a0f8&is=67724f78&hm=29349d7e624fcb150f298c40b15d68575d5bee22dace451856ea9da23e43db58&",
        "rarity": 12.5,
        "health": 6050,
        "damage": 2250,
    },
    {
        "name": "Hounder",
        "spawn_image_url": "https://media.discordapp.net/attachments/1322205679028670495/1322295423360176218/RobloxScreenShot20241227_210852940.png?ex=67725553&is=677103d3&hm=c32cad3bc0dc2ebc26cbdfeba7e8fb5ea83b55e557eafbfc3a0358a760654d7e&=&format=webp&quality=lossless",
        "card_image_url": "https://cdn.discordapp.com/attachments/1322202570529177642/1322293233815912498/CT-_Blau_1.png?ex=6773a4c9&is=67725349&hm=e37704c3fa30bc469f1b20c7bd7e18e25abe8c1d6bc06b1cbcd3b85d359d2c10&",
        "rarity": 9.5,
        "health": 9250,
        "damage": 4500,
    },
    {
        "name": "Pipopro",
        "spawn_image_url": "https://media.discordapp.net/attachments/1322205679028670495/1322977622778576976/artworks-OF3WFPHsapfnZrW8-lDiZAQ-t500x500.png?ex=67737f2d&is=67722dad&hm=1ec22c5b9af4c994af583de216afe05660c777e5437a738750577b9a49cbdf90&=&format=webp&quality=lossless",
        "card_image_url": "https://cdn.discordapp.com/attachments/1322202570529177642/1322977702105579591/Pipopro.png?ex=67737f3f&is=67722dbf&hm=2cc3c639f2e613963f78ec6dbfc274df6f6a74666d06461e4bfb60fdb5c3568d&",
        "rarity": 0.75,
        "health": 15000,
        "damage": 7500,
    },
    {
        "name": "Wilson",
        "spawn_image_url": "https://media.discordapp.net/attachments/1322205679028670495/1323344360879689730/RobloxScreenShot20241230_161947936.png?ex=67742bfa&is=6772da7a&hm=14a472045ae47f536705b91cb91bdae7ea52674d1cde2799ad65835c0c85d8df&=&format=webp&quality=lossless&width=532&height=350",
        "card_image_url": "https://media.discordapp.net/attachments/1322202570529177642/1323314295286665246/CC-.png?ex=67740ff9&is=6772be79&hm=54193da49212bd838fb47e993c16c2af1da3987a04373fc1a20def924f0744a6&=&format=webp&quality=lossless&width=479&height=671",
        "rarity": 1,
        "health": 9550,
        "damage": 4670,
    },
    {
        "name": "Stinger",
        "spawn_image_url": "https://media.discordapp.net/attachments/1322205679028670495/1323379787766698116/RobloxScreenShot20241230_205740938.png?ex=67744cf8&is=6772fb78&hm=ffe51d5793e02353736175578a9a6158e243b285a65649e695ba924a710c3c83&=&format=webp&quality=lossless&width=375&height=350",
        "card_image_url": "https://media.discordapp.net/attachments/1322202570529177642/1323383213451640862/Just_another_trooper_trying_to_stay_alive._He_doesnt_like_insurgents._His_left_arm_and_left_eye_are_gone_due_to_the_Gulag_13.png?ex=67745029&is=6772fea9&hm=c08cafd74fea97dcd3c7c6847ab940b55249ed62f0585149ca03e05c13ed6ea7&=&format=webp&quality=lossless&width=479&height=671",
        "rarity": 75,
        "health": 2150,
        "damage": 950,
    },
    {
        "name": "Sandy",
        "spawn_image_url": "https://media.discordapp.net/attachments/1322205679028670495/1323386530303053854/RobloxScreenShot20241230_211843002.png?ex=67745340&is=677301c0&hm=1679defda16cd577a0146f6dc1ce3e6e9bb08eac3934ecb6512a4a7711a34c09&=&format=webp&quality=lossless&width=522&height=350",
        "card_image_url": "https://media.discordapp.net/attachments/1322202570529177642/1323386408550928404/Just_another_trooper_trying_to_stay_alive._He_doesnt_like_insurgents._His_left_arm_and_left_eye_are_gone_due_to_the_Gulag_14.png?ex=67745323&is=677301a3&hm=dd52bd5a4777cc90d0f8a6793251192ac14a526e55037f3d2d32bb0db691471c&=&format=webp&quality=lossless&width=479&height=671",
        "rarity": 50,
        "health": 3000,
        "damage": 1950,
    },
    {
        "name": "Rancor",
        "spawn_image_url": "https://media.discordapp.net/attachments/1322205679028670495/1323561918878847047/RobloxScreenShot20241231_090056606.png?ex=6774f698&is=6773a518&hm=cffc47d9ab08a0b3d98df85ef86f7abf413be74c2b4f2ecc56ee520991ed5f7d&=&format=webp&quality=lossless",
        "card_image_url": "https://media.discordapp.net/attachments/1322202570529177642/1323563829925380166/Just_another_trooper_trying_to_stay_alive._He_doesnt_like_insurgents._His_left_arm_and_left_eye_are_gone_due_to_the_Gulag_15.png?ex=6774f85f&is=6773a6df&hm=d65e4c7ce98eb87dd896234a15a4a9d742d83fd44292fe1b0b392938a7bce01b&=&format=webp&quality=lossless&width=479&height=671",
        "rarity": 12.5,
        "health": 6950,
        "damage": 3050,
    },
    {
        "name": "Cooker",
        "spawn_image_url": "https://media.discordapp.net/attachments/1322205679028670495/1323570324767379497/RobloxScreenShot20241231_093357795.png?ex=6774fe6c&is=6773acec&hm=c75865e285d3d39f4a6476d442a01c9e1dbe3611a0b06cbd862c8c43b770e956&=&format=webp&quality=lossless&width=468&height=350",
        "card_image_url": "https://media.discordapp.net/attachments/1322202570529177642/1323573966652309504/Just_another_trooper_trying_to_stay_alive._He_doesnt_like_insurgents._His_left_arm_and_left_eye_are_gone_due_to_the_Gulag_17.png?ex=677501d0&is=6773b050&hm=8fe64e466f95254086fd222ad3698819eff00c38d7ab2333f132458ca25af856&=&format=webp&quality=lossless&width=479&height=671",
        "rarity": 17.5,
        "health": 5000,
        "damage": 2500,
    },
    {
        "name": "Longshot",
        "spawn_image_url": "https://media.discordapp.net/attachments/1322205679028670495/1323671916631949362/RobloxScreenShot20241231_161614848.png?ex=67755d09&is=67740b89&hm=cab4a3d1dba4eb57b42e592905780faaa24d5ffba9746ce3406325c7f520ef0d&=&format=webp&quality=lossless&width=480&height=350",
        "card_image_url": "https://media.discordapp.net/attachments/1322202570529177642/1323671828111298584/Just_another_trooper_trying_to_stay_alive._He_doesnt_like_insurgents._His_left_arm_and_left_eye_are_gone_due_to_the_Gulag_19.png?ex=67755cf4&is=67740b74&hm=05d5e4c11313875aea75d4c7e227bf32546af435d3755ebac0e66d817c11d2f5&=&format=webp&quality=lossless&width=479&height=671",
        "rarity": 70,
        "health": 2000,
        "damage": 650,
    },
    {
        "name": "Mertho",
        "spawn_image_url": "https://media.discordapp.net/attachments/1322205679028670495/1323578208863649863/RobloxScreenShot20241231_100652348.png?ex=677505c3&is=6773b443&hm=e8aad1e00d28942444ea357afa5b4ce2d0d4cd1949ad84e29fb99aae522be1f8&=&format=webp&quality=lossless&width=384&height=350",
        "card_image_url": "https://media.discordapp.net/attachments/1322202570529177642/1323672693647609937/Just_another_trooper_trying_to_stay_alive._He_doesnt_like_insurgents._His_left_arm_and_left_eye_are_gone_due_to_the_Gulag_21.png?ex=67755dc2&is=67740c42&hm=ddb0d3ac0879577f7497b50ccf367d6fe0afe12850451350bf7b79528dd56b49&=&format=webp&quality=lossless&width=479&height=671",
        "rarity": 70,
        "health": 1700,
        "damage": 500,
    },
    {
        "name": "Bricker",
        "spawn_image_url": "https://media.discordapp.net/attachments/1322205679028670495/1323674207355404338/RobloxScreenShot20241231_162811051.png?ex=6776b0ab&is=67755f2b&hm=469701c4cfe846ba2a1d409054169e50e4a38f2be05edb25e02bdb1037701ae5&=&format=webp&quality=lossless&width=490&height=350",
        "card_image_url": "https://media.discordapp.net/attachments/1322202570529177642/1323983294827597834/Just_another_trooper_trying_to_stay_alive._He_doesnt_like_insurgents._His_left_arm_and_left_eye_are_gone_due_to_the_Gulag_22.png?ex=67767f07&is=67752d87&hm=7d25ae8c7bbb0d950f02bc65458feec54d1c0d9587801257fc4d6f21f3ef920f&=&format=webp&quality=lossless&width=479&height=671",
        "rarity": 85,
        "health": 1550,
        "damage": 450,
    },
    {
        "name": "Sinner",
        "spawn_image_url": "https://media.discordapp.net/attachments/1322205679028670495/1323982617527451708/RobloxScreenShot20250101_125340765.png?ex=67767e66&is=67752ce6&hm=57ff065a4ae55a28e1a67ea0dfe6a55959924dd8c7f6c7375c6acb204bfcfb1f&=&format=webp&quality=lossless&width=318&height=350",
        "card_image_url": "https://media.discordapp.net/attachments/1322202570529177642/1323984903406354543/Just_another_trooper_trying_to_stay_alive._He_doesnt_like_insurgents._His_left_arm_and_left_eye_are_gone_due_to_the_Gulag_23.png?ex=67768087&is=67752f07&hm=c2a2e730930dc2aaa552e1aa40e0d4d01c7bc89aea1608b3c5c67319093fae68&=&format=webp&quality=lossless&width=479&height=671",
        "rarity": 77,
        "health": 2550,
        "damage": 1755,
    },
    {
        "name": "Voca",
        "spawn_image_url": "https://media.discordapp.net/attachments/1322205679028670495/1323987029956235304/RobloxScreenShot20250101_131047926.png?ex=67768282&is=67753102&hm=ec5f28ea32edcadee43190286cc5cdbe0d9197d69142a99813f2bc1e9c8d336f&=&format=webp&quality=lossless",
        "card_image_url": "https://media.discordapp.net/attachments/1322202570529177642/1323988014418104330/Just_another_trooper_trying_to_stay_alive._He_doesnt_like_insurgents._His_left_arm_and_left_eye_are_gone_due_to_the_Gulag_24.png?ex=6776836d&is=677531ed&hm=f57ab17956ed12fe5e9a1d4a326a09c83794975d06a5e305d386536a988b3c89&=&format=webp&quality=lossless&width=479&height=671",
        "rarity": 45,
        "health": 3750,
        "damage": 2050,
    },
    {
        "name": "Ren'dar Auron",
        "aliases": ["Rendar", "GONK"],
        "spawn_image_url": "https://media.discordapp.net/attachments/1322205679028670495/1323993493432959006/RobloxScreenShot20250101_133639131.png?ex=67768887&is=67753707&hm=e2cea043c4cec15a1d0ae8e31b6b03ff8629da7db01ad4d73133d61d4baef63b&=&format=webp&quality=lossless",
        "card_image_url": "https://media.discordapp.net/attachments/1322202570529177642/1323994036050071583/Just_another_trooper_trying_to_stay_alive._He_doesnt_like_insurgents._His_left_arm_and_left_eye_are_gone_due_to_the_Gulag_25.png?ex=67768908&is=67753788&hm=fd7bf7144407d5691bffc88739a40cdad0f19eb0a61bae6073dd563e9b94a77a&=&format=webp&quality=lossless&width=479&height=671",
        "rarity": 25,
        "health": 6500,
        "damage": 2850,
    },
    {
        "name": "Skye",
        "spawn_image_url": "https://media.discordapp.net/attachments/1322205679028670495/1323995408648638475/RobloxScreenShot20250101_134436877.png?ex=67768a50&is=677538d0&hm=bd6dd80b06ef660f4659867b68c4333beb25d7d9a715287f768032dc79951f49&=&format=webp&quality=lossless&width=419&height=350",
        "card_image_url": "https://media.discordapp.net/attachments/1322202570529177642/1323996389897797693/Just_another_trooper_trying_to_stay_alive._He_doesnt_like_insurgents._His_left_arm_and_left_eye_are_gone_due_to_the_Gulag_26.png?ex=67768b3a&is=677539ba&hm=c8013ba4445f32990c4f2e49e7aa7b346cfbaa78a0dac58d820d3acaf847b8b0&=&format=webp&quality=lossless&width=479&height=671",
        "rarity": 61,
        "health": 2700,
        "damage": 1500,
    }
]

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
@bot.command(name='set_spawn_mode')
@commands.has_permissions(administrator=True)
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

@tasks.loop(minutes=1)
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
    card = next((card for card in cards if card_name.lower() == card["name"].lower()), None)
    if card:
        embed = discord.Embed(title=f"Stats for {card['name']}", description="")
        embed.add_field(name="Health", value=card["health"], inline=True)
        embed.add_field(name="Damage", value=card["damage"], inline=True)
        embed.add_field(name="Rarity", value=f"{card['rarity']}%", inline=True)
        await ctx.send(embed=embed)
    else:
        await ctx.send("Card not found.")

# Command to initiate a fight between two players
@bot.command(name='fight')
async def fight(ctx, opponent: discord.Member):
    user_id = str(ctx.author.id)
    opponent_id = str(opponent.id)

    if user_id not in player_cards or not player_cards[user_id]:
        await ctx.send("You don't have any cards to fight with.")
        return

    if opponent_id not in player_cards or not player_cards[opponent_id]:
        await ctx.send(f"{opponent.mention} doesn't have any cards to fight with.")
        return

    user_card_name = random.choice(player_cards[user_id])
    opponent_card_name = random.choice(player_cards[opponent_id])

    user_card = next(card for card in cards if card["name"] == user_card_name)
    opponent_card = next(card for card in cards if card["name"] == opponent_card_name)

    user_health = user_card["health"]
    opponent_health = opponent_card["health"]

    battle_log = f"**{ctx.author.display_name}**'s **{user_card['name']}** vs **{opponent.display_name}**'s **{opponent_card['name']}**\n\n"

    while user_health > 0 and opponent_health > 0:
        opponent_health -= user_card["damage"]
        battle_log += f"**{user_card['name']}** attacks **{opponent_card['name']}** for {user_card['damage']} damage. **{opponent_card['name']}** has {max(opponent_health, 0)} health left.\n"
        if opponent_health <= 0:
            battle_log += f"\n**{user_card['name']}** wins!"
            break

        user_health -= opponent_card["damage"]
        battle_log += f"**{opponent_card['name']}** attacks **{user_card['name']}** for {opponent_card['damage']} damage. **{user_card['name']}** has {max(user_health, 0)} health left.\n"
        if user_health <= 0:
            battle_log += f"\n**{opponent_card['name']}** wins!"
            break

    await ctx.send(battle_log)


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
                await channel.send("235th dex going online")
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
    if user_id in player_cards and player_cards[user_id]:
        user_cards = player_cards[user_id]
        num_user_cards = len(user_cards)
        percentage = (num_user_cards / total_cards) * 100
        user_cards_list = '\n'.join(user_cards)
        await ctx.send(f"You have caught {num_user_cards} out of {total_cards} cards ({percentage:.2f}%).\n\nYour cards:\n{user_cards_list}")
    else:
        await ctx.send(f"You haven't caught any cards yet. There are {total_cards} cards available.")

def is_authorized(ctx):
    return str(ctx.author.id) in authorized_user_ids

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

# Respond to a simple message
@bot.command(name='hello')
async def hello(ctx):
    await ctx.send('Hello! I am the 235th dex!')

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
        '!print-stats - Shows the stats of a certain card.',
    ]
    commands_description = '\n'.join(commands_list)
    await ctx.send(f'Here is a list of all the commands you can use:\n{commands_description}')

#info, command to show the current release
@bot.command(name='info')
async def info(ctx):
    await ctx.send('Current release: beta') #expand later when we actually released the bot to the public




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
        asyncio.run(bot.run(token))
        logging.info(f'Logged in as {bot.user.name}')
    except Exception as e:
        logging.error(f'Error: {e}')