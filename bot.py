import os
import discord
from discord import Option, Embed
from discord.ext import commands
import yt_dlp as youtube_dl
import asyncio
from collections import deque
import random
from datetime import datetime
from dotenv import load_dotenv

# Configurações iniciais
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
PREFIX = os.getenv('DISCORD_PREFIX', '!')
DEFAULT_VOLUME = float(os.getenv('DEFAULT_VOLUME', 0.5))

# Configurações do yt-dlp
YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'extractaudio': True,
    'audioformat': 'mp3',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn -filter:a "volume={volume}"',
}

# Inicialização do bot
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents)

# Dicionários de estado
queues = {}
loops = {}
volumes = {}

class MusicPlayer:
    @staticmethod
    async def get_video_info(url):
        with youtube_dl.YoutubeDL(YTDL_OPTIONS) as ydl:
            info = ydl.extract_info(url, download=False)
            if 'entries' in info:
                info = info['entries'][0]
            return info

    @staticmethod
    async def create_audio_source(info, volume):
        ffmpeg_opts = FFMPEG_OPTIONS.copy()
        ffmpeg_opts['options'] = ffmpeg_opts['options'].format(volume=volume)
        return discord.FFmpegPCMAudio(info['url'], **ffmpeg_opts)

    @classmethod
    def get_queue(cls, guild_id):
        if guild_id not in queues:
            queues[guild_id] = deque(maxlen=20)
        return queues[guild_id]

    @classmethod
    async def play_next(cls, ctx):
        if loops.get(ctx.guild.id, False):
            await cls.play_song(ctx, cls.get_queue(ctx.guild.id)[0])
            return

        queue = cls.get_queue(ctx.guild.id)
        if queue:
            next_song = queue.popleft()
            await cls.play_song(ctx, next_song)

    @classmethod
    async def play_song(cls, ctx, song):
        try:
            info = await cls.get_video_info(song['webpage_url'])
            source = await cls.create_audio_source(info, volumes.get(ctx.guild.id, DEFAULT_VOLUME))
            
            ctx.voice_client.play(
                source,
                after=lambda e: asyncio.run_coroutine_threadsafe(
                    cls.play_next(ctx), bot.loop
                )
            )
            
            embed = Embed(
                title="🎵 Tocando agora",
                description=f"[{info['title']}]({info['webpage_url']})",
                color=discord.Color.blue()
            )
            embed.set_thumbnail(url=info.get('thumbnail'))
            embed.add_field(name="Duração", value=info.get('duration', 'N/A'))
            embed.add_field(name="Solicitado por", value=ctx.author.mention)
            await ctx.send(embed=embed)
        except Exception as e:
            error_embed = Embed(
                title="❌ Erro",
                description=f"Erro ao reproduzir: {str(e)}",
                color=discord.Color.red()
            )
            await ctx.send(embed=error_embed)
            await cls.play_next(ctx)

    @classmethod
    async def ensure_voice(cls, ctx):
        if not ctx.author.voice:
            await ctx.respond("Você precisa estar em um canal de voz!", ephemeral=True)
            return False
        
        if not ctx.voice_client:
            await ctx.author.voice.channel.connect()
        elif ctx.voice_client.channel != ctx.author.voice.channel:
            await ctx.respond("Entre no mesmo canal de voz que eu!", ephemeral=True)
            return False
        
        return True

# Comandos Slash
@bot.slash_command(name="tocar", description="Toca uma música do YouTube")
async def play(
    ctx: discord.ApplicationContext,
    busca: Option(str, "URL ou nome da música", required=True)
):
    await ctx.defer()
    
    if not await MusicPlayer.ensure_voice(ctx):
        return
    
    if not busca.startswith(('http://', 'https://')):
        busca = f"ytsearch:{busca}"
    
    try:
        info = await MusicPlayer.get_video_info(busca)
        if not info:
            await ctx.respond("Não encontrei essa música.", ephemeral=True)
            return
        
        queue = MusicPlayer.get_queue(ctx.guild.id)
        queue.append(info)
        
        if not ctx.voice_client.is_playing():
            await MusicPlayer.play_song(ctx, info)
        else:
            position = len(queue)
            embed = Embed(
                title="🎶 Adicionado à fila",
                description=f"[{info['title']}]({info['webpage_url']})",
                color=discord.Color.green()
            )
            embed.add_field(name="Posição", value=position)
            await ctx.respond(embed=embed)
    except Exception as e:
        await ctx.respond(f"Erro: {str(e)}", ephemeral=True)

@bot.slash_command(name="fila", description="Mostra a fila de reprodução")
async def queue(ctx: discord.ApplicationContext):
    queue = MusicPlayer.get_queue(ctx.guild.id)
    embed = Embed(title="🎶 Fila de Reprodução", color=discord.Color.blue())
    
    if ctx.voice_client.is_playing() and queue:
        embed.add_field(
            name="Tocando agora",
            value=f"[{queue[0]['title']}]({queue[0]['webpage_url']})",
            inline=False
        )
    
    if len(queue) > 1:
        songs = "\n".join(
            f"{i}. [{song['title']}]({song['webpage_url']})"
            for i, song in enumerate(queue[1:6], 1)
        )
        embed.add_field(
            name=f"Próximas ({len(queue)-1})",
            value=songs or "Vazio",
            inline=False
        )
    elif not queue:
        embed.description = "A fila está vazia"
    
    await ctx.respond(embed=embed)

@bot.slash_command(name="pular", description="Pula a música atual")
async def skip(ctx: discord.ApplicationContext):
    if not await MusicPlayer.ensure_voice(ctx):
        return
    
    if ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.respond("⏭ Pulou a música")
    else:
        await ctx.respond("Nada tocando para pular", ephemeral=True)

@bot.slash_command(name="pausar", description="Pausa a reprodução")
async def pause(ctx: discord.ApplicationContext):
    if not await MusicPlayer.ensure_voice(ctx):
        return
    
    if ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.respond("⏸ Música pausada")
    else:
        await ctx.respond("Nada tocando para pausar", ephemeral=True)

@bot.slash_command(name="continuar", description="Continua a reprodução")
async def resume(ctx: discord.ApplicationContext):
    if not await MusicPlayer.ensure_voice(ctx):
        return
    
    if ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.respond("▶ Música continuada")
    else:
        await ctx.respond("Nada pausado para continuar", ephemeral=True)

@bot.slash_command(name="volume", description="Ajusta o volume (0-100)")
async def volume(
    ctx: discord.ApplicationContext,
    nivel: Option(int, "Volume (0-100)", min_value=0, max_value=100)
):
    if not await MusicPlayer.ensure_voice(ctx):
        return
    
    volume = nivel / 100
    volumes[ctx.guild.id] = volume
    
    if ctx.voice_client.is_playing():
        current_song = MusicPlayer.get_queue(ctx.guild.id)[0]
        source = await MusicPlayer.create_audio_source(current_song, volume)
        ctx.voice_client.source = source
    
    await ctx.respond(f"🔊 Volume ajustado para {nivel}%")

@bot.slash_command(name="loop", description="Ativa/desativa o loop")
async def loop(ctx: discord.ApplicationContext):
    loops[ctx.guild.id] = not loops.get(ctx.guild.id, False)
    status = "✅ Ativado" if loops[ctx.guild.id] else "❌ Desativado"
    await ctx.respond(f"🔁 Loop {status}")

@bot.slash_command(name="embaralhar", description="Embaralha a fila")
async def shuffle(ctx: discord.ApplicationContext):
    queue = MusicPlayer.get_queue(ctx.guild.id)
    if len(queue) > 1:
        current = queue.popleft()
        shuffled = list(queue)
        random.shuffle(shuffled)
        queue.clear()
        queue.append(current)
        queue.extend(shuffled)
        await ctx.respond("🔀 Fila embaralhada")
    else:
        await ctx.respond("Não há músicas para embaralhar", ephemeral=True)

@bot.slash_command(name="limpar", description="Limpa a fila")
async def clear(ctx: discord.ApplicationContext):
    MusicPlayer.get_queue(ctx.guild.id).clear()
    await ctx.respond("🗑 Fila limpa")

@bot.slash_command(name="sair", description="Sai do canal de voz")
async def leave(ctx: discord.ApplicationContext):
    if ctx.voice_client:
        MusicPlayer.get_queue(ctx.guild.id).clear()
        await ctx.voice_client.disconnect()
        await ctx.respond("👋 Sai do canal de voz")
    else:
        await ctx.respond("Não estou em um canal de voz", ephemeral=True)

@bot.event
async def on_ready():
    print(f'Bot conectado como {bot.user}')
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.listening,
            name=f"{PREFIX}ajuda | música 🎵"
        )
    )
    await bot.sync_commands()  # Sincroniza os comandos slash

if __name__ == "__main__":
    bot.run(TOKEN)
