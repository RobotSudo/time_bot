import discord
from discord.ext import commands
import asyncio
from config import TOKEN

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

    # 🔥 Sync here (AFTER bot is ready)
    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} commands")
    except Exception as e:
        print("Sync error:", e)


async def load_cogs():
    await bot.load_extension("cogs.time_cog")
    await bot.load_extension("cogs.reply_cog")


async def main():
    async with bot:
        await load_cogs()
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
