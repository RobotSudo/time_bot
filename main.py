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

        await self.load_extension("cogs.time_cog")
        await self.load_extension("cogs.reply_cog")

        # THIS WAS MISSING
        await self.tree.sync()


bot = MyBot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")


if TOKEN:
    asyncio.run(bot.start(TOKEN))
else:
    print("❌ Missing DISCORD_TOKEN")
