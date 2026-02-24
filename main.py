import discord
from discord.ext import commands
import asyncio
from config import TOKEN
from database import setup_database

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

class MyBot(commands.Bot):
    async def setup_hook(self):
        await setup_database()

        # SAFE loading (won't double load)
        if "cogs.time_cog" not in self.extensions:
            await self.load_extension("cogs.time_cog")

        if "cogs.reply_cog" not in self.extensions:
            await self.load_extension("cogs.reply_cog")

bot = MyBot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

if TOKEN:
    asyncio.run(bot.start(TOKEN))
else:
    print("❌ Missing DISCORD_TOKEN")
