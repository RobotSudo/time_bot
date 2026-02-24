import discord
from discord.ext import commands
import asyncio
from config import TOKEN
from database import setup_database

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.presences = True  # Needed for status/activity features


class MyBot(commands.Bot):
    async def setup_hook(self):
        # Setup database
        await setup_database()

        # Load cogs
        await self.load_extension("cogs.time_cog")
        await self.load_extension("cogs.reply_cog")

        # Sync slash commands
        await self.tree.sync()


bot = MyBot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} ({bot.user.id})")


if TOKEN:
    asyncio.run(bot.start(TOKEN))
else:
    print("❌ DISCORD_TOKEN not set in environment.")
