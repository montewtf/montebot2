from typing import Literal, Optional
import discord
from discord.ext import commands
from discord import app_commands
import logging
import asyncio
import yt_dlp

intents = discord.Intents.default()
intents.message_content = True
token = open("token.txt", "r").read()
bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    application_id=760264219013677087,
    help_command=None)

def are_u_monte(ctx):
    return ctx.author.id == 125782351065251840

@bot.event
async def on_ready():
    print(f'{bot.user} is ready')

@bot.command(hidden=True)
@commands.check(are_u_monte)
async def load(ctx, extension):
    await bot.load_extension(extension)
    print(extension+" loaded")
    
@bot.command(hidden=True)
@commands.check(are_u_monte)
async def unload(ctx, extension):
    await bot.unload_extension(extension)
    print(extension+" unloaded")
    
@bot.command(hidden=True)
@commands.check(are_u_monte)
async def reload(ctx, extension):
    await bot.reload_extension(extension)
    print(extension+" reloaded")
    
@bot.command(hidden=True)
@commands.check(are_u_monte)
async def sync(ctx: commands.Context, guilds: commands.Greedy[discord.Object], spec: Optional[Literal["~", "*", "^"]] = None) -> None:
    if not guilds:
        if spec == "~":
            synced = await ctx.bot.tree.sync(guild=ctx.guild)
        elif spec == "*":
            ctx.bot.tree.copy_global_to(guild=ctx.guild)
            synced = await ctx.bot.tree.sync(guild=ctx.guild)
        elif spec == "^":
            ctx.bot.tree.clear_commands(guild=ctx.guild)
            await ctx.bot.tree.sync(guild=ctx.guild)
            synced = []
        else:
            synced = await ctx.bot.tree.sync()
        await ctx.send(
            f"Synced {len(synced)} commands {'globally' if spec is None else 'to the current guild.'}"
        )
        return
    ret = 0
    for guild in guilds:
        try:
            await ctx.bot.tree.sync(guild=guild)
        except discord.HTTPException:
            pass
        else:
            ret += 1
    await ctx.send(f"Synced the tree to {ret}/{len(guilds)}.")

async def main():
    async with bot:
        await bot.load_extension("music")
        await bot.start(token)

asyncio.run(main())
