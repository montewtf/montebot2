from typing import List, Dict
import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import yt_dlp
import requests
import urllib.parse, urllib.request
import re
import time
import os
from threading import Event
from pytube import Playlist

sessions = {}
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
    async def from_url(cls, url):
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=True))
        filename = ytdl.prepare_filename(data)
        return cls(discord.FFmpegOpusAudio(filename, **ffmpeg_options), data)

class ServerSession:
    def __init__(self, guild_id, voice_client, bot):
        self.guild_id: int = guild_id
        self.voice_client: discord.VoiceClient = voice_client
        self.bot = bot
        self.queue: List[YTDLSource] = []
        self.current = None

    def display_queue(self) -> str:
        currently_playing = f'**Currently playing:** \n{self.current}'
        return currently_playing + '\n**Queue:**\n' + '\n'.join([f'{i + 1}. {s}' for i, s in enumerate(self.queue)])
        
    async def add_to_queue(self, interaction, url):
        sources_added = []
        yt_source = await YTDLSource.from_url(url)
        self.queue.append(yt_source)
        if not self.voice_client.is_playing():
            await self.start_playing(interaction)
        else:
            return yt_source.title
            
    async def start_playing(self, interaction):
        print('check: in start_playing')
        self.voice_client.play(self.queue[0].audio_source, after=lambda e=None: asyncio.run_coroutine_threadsafe(self.after_playing(interaction, e), self.bot.loop))
        self.current = self.queue.pop(0)
        print('check: done_playing')
        
    async def after_playing(self, interaction, error):
        if error:
            raise error
        elif self.voice_client.is_connected():
            if self.queue:
                await self.play_next(interaction)
            else:
                self.heartbeat = heartbeat = time.time()
                await asyncio.sleep(30)
                if self.voice_client.is_connected() and not self.voice_client.is_playing() and self.heartbeat == heartbeat:
                    await disconnect(interaction.guild_id)
                
    async def play_next(self, interaction):
        if self.queue:
            self.voice_client.play(self.queue[0].audio_source, after=lambda e=None: asyncio.run_coroutine_threadsafe(self.after_playing(interaction, e), self.bot.loop))
            self.current = self.queue.pop(0)
            
sessions: Dict[int, ServerSession] = {}

def clean_cache_files():
    if not sessions:
        for file in os.listdir():
            if os.path.splitext(file)[1] in ['.webm', '.mp4', '.m4a', '.mp3', '.ogg']:
                os.remove(file)

async def disconnect(guildid):
        voice_client = sessions[guildid].voice_client
        await voice_client.disconnect()
        del sessions[guildid]
        clean_cache_files()

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    async def join_server(self, interaction: discord.Interaction, channel):
        voice_client = await channel.connect()
        if voice_client.is_connected():
            sessions[interaction.guild_id] = ServerSession(interaction.guild_id, voice_client, self.bot)
            print(f'check: connected to {interaction.guild_id}')
            return sessions[interaction.guild_id]
        else:
            print('check: notconnected')
            interaction.response.send_message(f'Failed to connect to voice channel {interaction.user.voice.channel.name}.')
    
    @app_commands.command(name="stop")
    async def stop(self, interaction: discord.Interaction):
        guildid = interaction.guild_id
        if guildid in sessions: 
            voice_client = sessions[guildid].voice_client
            await disconnect(guildid)
            await interaction.response.send_message(f'Disconnected from {voice_client.channel.name}.')
    
    @app_commands.command(name='skip')
    async def skip(self, interaction: discord.Interaction):
        guildid = interaction.guild_id
        if guildid in sessions:
            session = sessions[guildid]
            voice_client = session.voice_client
            if voice_client.is_playing():
                if len(session.queue) > 0:
                    await interaction.response.send_message('Skipped')
                    voice_client.stop()
                else:
                    await interaction.response.send_message('This is already the last item in the queue! Use `/stop` to stop playing')
            
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
            print('in query')
            if query.lower() == 'calypso':
                url = 'https://www.youtube.com/watch?v=67Iw_OsuMcc'
            else:
                query_string = urllib.parse.urlencode({"search_query": query})
                formatUrl = urllib.request.urlopen("https://www.youtube.com/results?" + query_string)
                search_results = re.findall(r"((watch\?v=|shorts/)\S{11})", formatUrl.read().decode())
                url = f'https://www.youtube.com/{search_results[0][0]}'
            print('done query')
        else:
            print('check: is url')
            url = query
        await interaction.response.send_message(f'Attempting to play {url}')
        sources_added = []
        if 'playlist' in url:
            p = Playlist(url)
            for p_url in p.video_urls:
                source_title = await session.add_to_queue(interaction, p_url)
                if source_title != None:
                    sources_added.append(source_title)
        else:
            source_title = await session.add_to_queue(interaction, url)
            if source_title != None:
                sources_added.append(source_title)
        if sources_added:
            queue_string = '\n* ' + '\n* '.join(sources_added)
            await interaction.followup.send(f'Added to queue:{queue_string}')
        print('check: added to queue')
    
async def setup(bot):
    await bot.add_cog(Music(bot))
