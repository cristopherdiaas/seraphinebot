import os
import discord
from discord import Option, Embed
from discord.ext import commands
import yt_dlp as youtube_dl
import asyncio
from collections import deque
import random
from discord import Option

# ...

busca = Option(str, "URL ou nome da música", required=True)
from datetime import datetime
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

# Configurações
TOKEN = os.getenv('DISCORD_TOKEN')
PREFIX = os.getenv('DISCORD_PREFIX', '!')
DEFAULT_VOLUME = float(os.getenv('DEFAULT_VOLUME', 0.5))
MAX_QUEUE_SIZE = 20

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

# Inicializar o bot
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents)

# Dicionários para armazenar estados
queues = {}
loops = {}
volumes = {}

class MusicBot:
    @staticmethod
    async def get_video_info(url):
        with youtube_dl.YoutubeDL(YTDL_OPTIONS) as ydl:
            info = ydl.extract_info(url, download=False)
            if 'entries' in info:
                info = info['entries'][0]
            return info

    @staticmethod
    async def create_source(info, volume):
        ffmpeg_opts = FFMPEG_OPTIONS.copy()
        ffmpeg_opts['options'] = ffmpeg_opts['options'].format(volume=volume)
        return discord.FFmpegPCMAudio(info['url'], **ffmpeg_opts)

    @staticmethod
    def get_queue(guild_id):
        if guild_id not in queues:
            queues[guild_id] = deque(maxlen=MAX_QUEUE_SIZE)
        return queues[guild_id]

    @staticmethod
    def get_loop(guild_id):
        return loops.get(guild_id, False)

    @staticmethod
    def get_volume(guild_id):
        return volumes.get(guild_id, DEFAULT_VOLUME)

    @staticmethod
    def create_embed(title, description, color):
        embed = Embed(
            title=title,
            description=description,
            color=color,
            timestamp=datetime.utcnow()
        )
        return embed

    @classmethod
    async def play_next(cls, ctx):
        if cls.get_loop(ctx.guild.id):
            current_song = cls.get_queue(ctx.guild.id)[0]
            await cls.play_song(ctx, current_song)
            return

        queue = cls.get_queue(ctx.guild.id)
        if queue:
            next_song = queue.popleft()
            await cls.play_song(ctx, next_song)

    @classmethod
    async def play_song(cls, ctx, song):
        try:
            info = await cls.get_video_info(song['webpage_url'])
            source = await cls.create_source(info, cls.get_volume(ctx.guild.id))
            
            ctx.voice_client.play(
                source,
                after=lambda e: asyncio.run_coroutine_threadsafe(
                    cls.play_next(ctx), bot.loop
                )
            )
            
            embed = cls.create_embed(
                "🎵 Tocando agora",
                f"[{info['title']}]({info['webpage_url']})",
                discord.Color.blue()
            )
            embed.set_thumbnail(url=info.get('thumbnail', ''))
            embed.add_field(name="Duração", value=info.get('duration_str', 'N/A'))
            embed.add_field(name="Solicitado por", value=ctx.author.mention)
            await ctx.send(embed=embed)
        except Exception as e:
            error_embed = cls.create_embed(
                "❌ Erro",
                f"Não foi possível reproduzir a música: {str(e)}",
                discord.Color.red()
            )
            await ctx.send(embed=error_embed)
            await cls.play_next(ctx)

    @classmethod
    async def ensure_voice(cls, ctx):
        if not ctx.author.voice:
            embed = cls.create_embed(
                "❌ Erro",
                "Você precisa estar em um canal de voz!",
                discord.Color.red()
            )
            await ctx.respond(embed=embed, ephemeral=True)
            return False
        
        if not ctx.voice_client:
            await ctx.author.voice.channel.connect()
        elif ctx.voice_client.channel != ctx.author.voice.channel:
            embed = cls.create_embed(
                "❌ Erro",
                "Você precisa estar no mesmo canal de voz que eu!",
                discord.Color.red()
            )
            await ctx.respond(embed=embed, ephemeral=True)
            return False
        
        return True

# Comandos Slash
@bot.slash_command(name="tocar", description="Toca uma música do YouTube")
async def tocar(
    ctx,
    busca: str = Option("URL ou nome da música", required=True)
):
    await ctx.defer()
    
    if not await MusicBot.ensure_voice(ctx):
        return
    
    # Verifica se é URL ou busca
    if not busca.startswith(('http://', 'https://')):
        busca = f"ytsearch:{busca}"
    
    try:
        info = await MusicBot.get_video_info(busca)
        if not info:
            embed = MusicBot.create_embed(
                "❌ Erro",
                "Não foi possível encontrar a música.",
                discord.Color.red()
            )
            await ctx.respond(embed=embed, ephemeral=True)
            return
        
        queue = MusicBot.get_queue(ctx.guild.id)
        queue.append(info)
        
        if not ctx.voice_client.is_playing():
            await MusicBot.play_song(ctx, info)
        else:
            position = len(queue)
            embed = MusicBot.create_embed(
                "🎶 Adicionado à fila",
                f"[{info['title']}]({info['webpage_url']})",
                discord.Color.green()
            )
            embed.add_field(name="Posição na fila", value=position)
            await ctx.respond(embed=embed)
    except Exception as e:
        embed = MusicBot.create_embed(
            "❌ Erro",
            f"Ocorreu um erro: {str(e)}",
            discord.Color.red()
        )
        await ctx.respond(embed=embed, ephemeral=True)

@bot.slash_command(name="pular", description="Pula a música atual")
async def pular(ctx):
    if not await MusicBot.ensure_voice(ctx):
        return
    
    if ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.respond("⏭ Música pulada")
    else:
        embed = MusicBot.create_embed(
            "❌ Erro",
            "Nenhuma música está tocando no momento",
            discord.Color.red()
        )
        await ctx.respond(embed=embed, ephemeral=True)

@bot.slash_command(name="fila", description="Mostra a fila de músicas")
async def fila(ctx):
    queue = MusicBot.get_queue(ctx.guild.id)
    if not queue and not ctx.voice_client.is_playing():
        embed = MusicBot.create_embed(
            "🎶 Fila de Reprodução",
            "A fila está vazia",
            discord.Color.blue()
        )
        await ctx.respond(embed=embed)
        return
    
    embed = MusicBot.create_embed(
        "🎶 Fila de Reprodução",
        "",
        discord.Color.blue()
    )
    
    if ctx.voice_client.is_playing():
        current_song = queue[0] if queue else None
        if current_song:
            embed.add_field(
                name="Tocando agora",
                value=f"[{current_song['title']}]({current_song['webpage_url']})",
                inline=False
            )
    
    if len(queue) > 1:
        queue_list = "\n".join(
            f"{i}. [{song['title']}]({song['webpage_url']})"
            for i, song in enumerate(queue[1:11], 1)
        )
        embed.add_field(
            name=f"Próximas músicas ({len(queue)-1})",
            value=queue_list,
            inline=False
        )
    
    await ctx.respond(embed=embed)

@bot.slash_command(name="pausar", description="Pausa a música atual")
async def pausar(ctx):
    if not await MusicBot.ensure_voice(ctx):
        return
    
    if ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.respond("⏸ Música pausada")
    else:
        embed = MusicBot.create_embed(
            "❌ Erro",
            "Nenhuma música está tocando no momento",
            discord.Color.red()
        )
        await ctx.respond(embed=embed, ephemeral=True)

@bot.slash_command(name="continuar", description="Continua a música pausada")
async def continuar(ctx):
    if not await MusicBot.ensure_voice(ctx):
        return
    
    if ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.respond("▶ Música continuada")
    else:
        embed = MusicBot.create_embed(
            "❌ Erro",
            "A música não está pausada",
            discord.Color.red()
        )
        await ctx.respond(embed=embed, ephemeral=True)

@bot.slash_command(name="volume", description="Ajusta o volume (0-100)")
async def volume(
    ctx,
    volume: int = Option("Volume (0-100)", min_value=0, max_value=100)
):
    if not await MusicBot.ensure_voice(ctx):
        return
    
    volume = volume / 100
    volumes[ctx.guild.id] = volume
    
    if ctx.voice_client.is_playing():
        current_song = MusicBot.get_queue(ctx.guild.id)[0]
        source = await MusicBot.create_source(current_song, volume)
        ctx.voice_client.source = source
    
    await ctx.respond(f"🔊 Volume ajustado para {int(volume*100)}%")

@bot.slash_command(name="loop", description="Ativa/desativa o loop da música atual")
async def loop(ctx):
    loops[ctx.guild.id] = not MusicBot.get_loop(ctx.guild.id)
    status = "ativado" if loops[ctx.guild.id] else "desativado"
    await ctx.respond(f"🔁 Loop {status}")

@bot.slash_command(name="embaralhar", description="Embaralha a fila de músicas")
async def embaralhar(ctx):
    queue = MusicBot.get_queue(ctx.guild.id)
    if len(queue) > 1:
        current_song = queue.popleft()
        shuffled = list(queue)
        random.shuffle(shuffled)
        queue.clear()
        queue.append(current_song)
        queue.extend(shuffled)
        await ctx.respond("🔀 Fila embaralhada")
    else:
        embed = MusicBot.create_embed(
            "❌ Erro",
            "Não há músicas suficientes na fila para embaralhar",
            discord.Color.red()
        )
        await ctx.respond(embed=embed, ephemeral=True)

@bot.slash_command(name="limpar", description="Limpa a fila de músicas")
async def limpar(ctx):
    MusicBot.get_queue(ctx.guild.id).clear()
    await ctx.respond("🗑 Fila limpa")

@bot.slash_command(name="sair", description="Desconecta o bot do canal de voz")
async def sair(ctx):
    if ctx.voice_client:
        MusicBot.get_queue(ctx.guild.id).clear()
        await ctx.voice_client.disconnect()
        await ctx.respond("👋 Desconectado do canal de voz")
    else:
        embed = MusicBot.create_embed(
            "❌ Erro",
            "Não estou conectado a nenhum canal de voz",
            discord.Color.red()
        )
        await ctx.respond(embed=embed, ephemeral=True)

@bot.event
async def on_ready():
    print(f'Bot conectado como {bot.user}')
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.listening,
            name=f"{PREFIX}ajuda | música 🎵"
        )
    )

# Iniciar o bot
if __name__ == "__main__":
    bot.run(TOKEN)