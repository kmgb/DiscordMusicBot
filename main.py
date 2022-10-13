# This example requires the "message_content" privileged intent to function.

import asyncio
import logging
import os

import discord
import youtube_dl

from discord.ext import commands
from dotenv import load_dotenv

# Suppress noise about console usage from errors
youtube_dl.utils.bug_reports_message = lambda: ""


ytdl_format_options = {
    "format": "bestaudio/best[abr<=75]",  # TODO: Determine if the abr selector works
    "outtmpl": "%(extractor)s-%(id)s-%(title)s.%(ext)s",
    "restrictfilenames": True,
    "noplaylist": True,
    "nocheckcertificate": True,
    "ignoreerrors": False,
    "logtostderr": False,
    "quiet": True,
    "no_warnings": True,
    "default_search": "auto",
    "source_address": "0.0.0.0",  # bind to ipv4 since ipv6 addresses cause issues sometimes
}

ffmpeg_options = {
    "options": "-vn",  # TODO: does -bufsize 2 work?
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)


class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)

        self.data = data

        self.title = data.get("title")
        self.url = data.get("url")

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))

        if "entries" in data:
            # take first item from a playlist
            data = data["entries"][0]

        filename = data["url"] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)


class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.queue = []

    @commands.command()
    async def join(self, ctx, *, channel: discord.VoiceChannel = None):
        """Joins a voice channel"""

        if ctx.voice_client is not None:
            return await ctx.voice_client.move_to(channel)

        if channel is None:
            if ctx.author.voice:
                await ctx.author.voice.channel.connect()
            else:
                await ctx.send("You are not connected to a voice channel.")
                raise commands.CommandError("Author not connected to a voice channel.")

        else:
            await channel.connect()

    @commands.command()
    async def play(self, ctx, *, url):
        """Streams from a url or adds to queue"""

        if ctx.voice_client.is_playing():
            self.queue.append(url)
            print(f"Added song to queue as we're already playing something, queue={self.queue}")
            await ctx.send("Added to queue")
        else:
            async with ctx.typing():
                await self.play_song(ctx, url)

    @commands.command(aliases=["next"])
    async def skip(self, ctx):
        print("Skipping by user request")
        # Note: this causes the `after` function to be invoked, which is on_finish_streaming
        ctx.voice_client.stop()

    @commands.command()
    async def clear(self, ctx):
        print("Clearing queue by user request")

        self.queue.clear()
        ctx.send("Cleared queue")

    def on_finish_streaming(self, ctx, e=None):
        """When we're done with a song, we play the next one, if available"""
        if e:
            print(f"Player error: {e}")

        print(f"Finished streaming, remaining queue: {self.queue}")

        if self.queue:
            url = self.queue.pop(0)
            # Execute an async function from this synchronous callback:
            asyncio.run_coroutine_threadsafe(self.play_song(ctx, url), self.bot.loop)

    async def play_song(self, ctx, url):
        print(f"Playing song: {url}")

        player = await YTDLSource.from_url(url, loop=self.bot.loop, stream=True)
        ctx.voice_client.play(player, after=lambda e: self.on_finish_streaming(ctx, e))

        # Disable mentions because video titles could contain @everyone
        await ctx.send(f"Now playing: {player.title}",
                       allowed_mentions=discord.AllowedMentions.none())

    @commands.command(aliases=["leave", "quit", "exit", "end"])
    async def stop(self, ctx):
        """Stops and disconnects the bot from voice"""

        await ctx.voice_client.disconnect()

    @play.before_invoke
    async def ensure_voice(self, ctx):
        if ctx.voice_client is None:

            if ctx.author.voice:
                await ctx.author.voice.channel.connect()
            else:
                await ctx.send("You are not connected to a voice channel.")
                raise commands.CommandError("Author not connected to a voice channel.")

    # TODO: AFK timer before disconnecting and clearing queue


intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix=commands.when_mentioned_or("!"),
    description="Simple music bot with queueing",
    intents=intents,
)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("------")

    await bot.change_presence(
        activity=discord.Activity(type=discord.ActivityType.listening, name="!play")
    )


async def main():
    load_dotenv()

    async with bot:
        await bot.add_cog(Music(bot))
        await bot.start(os.environ.get("DISCORD_TOKEN"))


discord.utils.setup_logging(level=logging.INFO, root=False)
asyncio.run(main())
