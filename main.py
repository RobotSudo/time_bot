import discord
from discord.ext import commands
from config import TOKEN
from database import setup_database

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

async def main():
    await setup_database()

    await bot.load_extension("cogs.time_cog")
    await bot.load_extension("cogs.reply_cog")

    await bot.start(TOKEN)

if TOKEN:
    import asyncio
    asyncio.run(main())
else:
    print("❌ Missing DISCORD_TOKEN")
