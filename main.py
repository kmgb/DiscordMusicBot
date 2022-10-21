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
        """Joins a voice channel -- the one you're in, or the one you specify"""

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
        """Streams music from a url or adds to the queue"""

        if ctx.voice_client.is_playing():
            self.queue.append(url)
            print(f"Added song to queue as we're already playing something, queue={self.queue}")
            await ctx.send("Added to queue")
        else:
            async with ctx.typing():
                await self.play_song(ctx, url)

    @commands.command(aliases=["next"])
    async def skip(self, ctx):
        """Skips the current song"""

        print("Skipping by user request")
        # Note: this causes the `after` function to be invoked, which is on_finish_streaming
        ctx.voice_client.stop()

    @commands.command()
    async def clear(self, ctx):
        """Clear the queue"""

        print("Clearing queue by user request")

        self.clear_queue()
        await ctx.send("Cleared queue")

    def on_finish_streaming(self, ctx, e=None):
        """When we're done with a song, we play the next one, if available"""

        if e:
            print(f"Player error: {e}")

        print(f"Finished streaming, remaining queue: {self.queue}")

        if not ctx.voice_client:
            print("No more voice client, skipping playing the next song")
            return

        if self.queue:
            url = self.queue.pop(0)
            # Execute an async function from this synchronous callback:
            asyncio.run_coroutine_threadsafe(self.play_song(ctx, url), self.bot.loop)

    async def play_song(self, ctx, url):
        print(f"Playing song: {url}")

        player = await YTDLSource.from_url(url, loop=self.bot.loop, stream=True)
        ctx.voice_client.play(player, after=lambda e: self.on_finish_streaming(ctx, e))

        title = player.title
        title = discord.utils.escape_markdown(title)
        title = discord.utils.escape_mentions(title)
        # TODO: Sanitize links in youtube titles?

        # Disable mentions. Even if we escape them, there could still be some input that
        # triggers an @everyone due to a bug.
        await ctx.send(f"Now playing: {title}",
                       allowed_mentions=discord.AllowedMentions.none())

    def clear_queue(self):
        self.queue.clear()

    @commands.command(aliases=["leave", "quit", "exit", "end"])
    async def stop(self, ctx):
        """Stops and disconnects the bot from voice"""

        await self.clear(ctx)

        if ctx.voice_client:
            await ctx.voice_client.disconnect()

    @play.before_invoke
    async def ensure_voice(self, ctx):
        if ctx.voice_client is None:
            if ctx.author.voice:
                await ctx.author.voice.channel.connect()
            else:
                await ctx.send("You are not connected to a voice channel.")
                raise commands.CommandError("Author not connected to a voice channel.")

    @commands.Cog.listener(name="on_command")
    async def log_command(self, ctx):
        print(f"Command issued: {ctx.guild.name} > {ctx.author} > {ctx.command} [{ctx.message.content}]")


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


@bot.event
async def on_message(message: discord.Message):
    # Filter out DMs from command processing
    if message.guild:
        await bot.process_commands(message)


@bot.event
async def on_voice_state_update(member, before, after):
    if not bot.voice_clients:
        return

    print("Voice state update")

    for client in bot.voice_clients:
        if len(client.channel.members) <= 1:
            print("Left alone in voice channel, leaving")
            bot.get_cog("Music").clear_queue()
            await client.disconnect()


async def main():
    load_dotenv()

    async with bot:
        await bot.add_cog(Music(bot))
        await bot.start(os.environ.get("DISCORD_TOKEN"))


discord.utils.setup_logging(level=logging.INFO, root=False)
asyncio.run(main())
