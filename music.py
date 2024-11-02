from typing import List, Dict
import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import yt_dlp
import requests
import urllib.parse, urllib.request
import re

queues = {}
yt_dl_options = {"format": "bestaudio/best"}
ytdl = yt_dlp.YoutubeDL(yt_dl_options)
ffmpeg_options = {'options': '-vn -sn -filter:a "volume=0.1"'}

class YTDLSource:
    def __init__(self, source: discord.AudioSource, data):
        self.audio_source = source
        self.data = data
        self.title: str = data.get('title')
        self.url: str = data.get('webpage_url')
        
    def __str__(self):
        return f'{self.title} `{self.url}`'
        
    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegOpusAudio(filename, **ffmpeg_options), data)

class ServerSession:
    def __init__(self, guild_id, voice_client):
        self.guild_id: int = guild_id
        self.voice_client: discord.VoiceClient = voice_client
        self.queue: List[YTDLSource] = []

    def display_queue(self) -> str:
        currently_playing = f'Currently playing: 0. {self.queue[0]}'
        return currently_playing + '\n' + '\n'.join([f'{i + 1}. {s}' for i, s in enumerate(self.queue[1:])])
        
    async def add_to_queue(self, interaction, url):
        print('check: in add_to_queue')
        yt_source = await YTDLSource.from_url(url, loop=None, stream=False)
        if self.voice_client.is_playing():
            await interaction.followup.send(f'Added to queue: {yt_source.title} #{len(self.queue)}')
        print('check: made yt_source')
        self.queue.append(yt_source)
        print('check: added to queue')
            
    async def start_playing(self, interaction):
        print('check: in start_playing')
        print(self.queue[0].audio_source)
        print(self.voice_client)
        self.voice_client.play(self.queue[0].audio_source, after=lambda e=None: asyncio.run(self.after_playing(interaction, e)))
        print('check: done_playing(broke)')
        
    async def after_playing(self, interaction, error):
        if error:
            raise error
        else:
            if self.queue:
                await self.play_next(interaction)
                
    async def play_next(self, interaction):
        self.queue.pop(0)
        if self.queue:
            await self.voice_client.play(self.queue[0].audio_source, after=lambda e=None: asyncio.run(self.after_playing(interaction, e)))
            
sessions: Dict[int, ServerSession] = {}

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    async def join_server(self, interaction: discord.Interaction, channel):
        voice_client = await channel.connect()
        if voice_client.is_connected():
            sessions[interaction.guild_id] = ServerSession(interaction.guild_id, voice_client)
            print('check: connected')
            return sessions[interaction.guild_id]
        else:
            print('check: notconnected')
            interaction.response.send_message(f'Failed to connect to voice channel {interaction.user.voice.channel.name}.')
    
    @app_commands.command(name="stop")
    async def disconnect(self, interaction: discord.Interaction):
        guildid = interaction.guild_id
        if guildid in sessions:
            voice_client = sessions[guildid].voice_client
            await voice_client.disconnect()
            await interaction.response.send_message(f'Disconnected from {voice_client.channel.name}.')
            voice_client.cleanup()
            del sessions[guildid]
    
    @app_commands.command(name='skip')
    async def skip(self, interaction: discord.Interaction):
        guildid = interaction.guild_id
        if guildid in sessions:
            session = sessions[guildid]
            voice_client = session.voice_client
            if voice_client.is_playing():
                if len(session.queue) > 1:
                    await interaction.response.send_message('Skipped')
                    voice_client.stop()
                else:
                    await interaction.response.send_message('This is already the last item in the queue!')
            
    @app_commands.command(name='queue')
    async def show_queue(self, interaction: discord.Interaction):
        guildid = interaction.guild_id
        if guildid in sessions:
            await interaction.response.send_message(f'{sessions[guildid].display_queue()}')
    
    @app_commands.command(name="play")
    async def play(self, interaction: discord.Interaction, query: str):
        guildid = interaction.guild_id
        if guildid not in sessions:
            if interaction.user.voice is None:
                await interaction.response.send_message('You are not connected to any voice channel!')
                return
            else:
                session = await self.join_server(interaction, interaction.user.voice.channel)
        else:
            session = sessions[guildid]
            if session.voice_client.channel != interaction.user.voice.channel:
                await session.voice_client.move_to(interaction.user.voice.channel)
        print('check: pre query')
        try:
            requests.get(query)
        except (requests.ConnectionError, requests.exceptions.MissingSchema):
            print('query1')
            query_string = urllib.parse.urlencode({"search_query": query})
            print('query2')
            formatUrl = urllib.request.urlopen("https://www.youtube.com/results?" + query_string)
            print('query3')
            search_results = re.findall(r"watch\?v=(\S{11})", formatUrl.read().decode())
            print('query4')
            url = f'https://www.youtube.com/watch?v={search_results[0]}'
            print('query5')
            if query.lower() == 'calypso':
                url = 'https://www.youtube.com/watch?v=67Iw_OsuMcc'
        else:
            print('check: is url')
            url = query
        await interaction.response.send_message(f'Attempting to play {url}')
        await session.add_to_queue(interaction, url)
        print('check: added to queue2')
        if not session.voice_client.is_playing() and len(session.queue) <= 1:
            print('check: about to start playing')
            await session.start_playing(interaction)

async def setup(bot):
    await bot.add_cog(Music(bot))
