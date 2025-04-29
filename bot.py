import os
import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp as youtube_dl
import asyncio
from collections import deque
from dotenv import load_dotenv
import random

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

intents = discord.Intents.default()
intents.voice_states = True
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Configurações do yt-dlp
ytdl_format_options = {
    'format': 'bestaudio/best',
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

ffmpeg_options = {
    'options': '-vn',
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

class MusicQueue:
    def __init__(self):
        self.queue = deque()
        self.loop = False
        self.volume = 0.5

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')
        self.duration = data.get('duration')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=True):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        
        if 'entries' in data:
            data = data['entries'][0]
            
        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data)

# Dicionário para armazenar filas por servidor
queues = {}

def get_queue(guild_id):
    if guild_id not in queues:
        queues[guild_id] = MusicQueue()
    return queues[guild_id]

async def play_next(ctx):
    queue = get_queue(ctx.guild.id)
    
    if queue.loop and queue.queue:
        # Repete a música atual se o loop estiver ativado
        await play_song(ctx, queue.queue[0])
        return
    
    if queue.queue:
        next_song = queue.queue.popleft()
        await play_song(ctx, next_song)

async def play_song(ctx, song):
    try:
        ctx.voice_client.play(song, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop))
        await ctx.send(f"🎵 Tocando agora: **{song.title}**")
    except Exception as e:
        await ctx.send(f"❌ Erro ao reproduzir: {str(e)}")
        await play_next(ctx)

@bot.tree.command(name="play", description="Toca uma música do YouTube")
@app_commands.describe(query="Nome da música ou URL")
async def play(interaction: discord.Interaction, query: str):
    """Toca música do YouTube por nome ou URL"""
    await interaction.response.defer()
    
    if not interaction.user.voice:
        return await interaction.followup.send("Você precisa estar em um canal de voz!")
    
    try:
        voice_client = interaction.guild.voice_client
        if not voice_client:
            voice_client = await interaction.user.voice.channel.connect()
        elif voice_client.channel != interaction.user.voice.channel:
            return await interaction.followup.send("Já estou em outro canal de voz!")
            
        # Busca a música
        player, data = await YTDLSource.from_url(query, loop=bot.loop, stream=True)
        queue = get_queue(interaction.guild.id)
        
        if voice_client.is_playing() or voice_client.is_paused():
            queue.queue.append(player)
            return await interaction.followup.send(f"🎶 Adicionado à fila (#{len(queue.queue)}): **{data['title']}**")
        
        queue.queue.append(player)
        await play_song(interaction, player)
        
    except Exception as e:
        await interaction.followup.send(f"❌ Erro: {str(e)}")

@bot.tree.command(name="skip", description="Pula a música atual")
async def skip(interaction: discord.Interaction):
    """Pula para a próxima música na fila"""
    voice_client = interaction.guild.voice_client
    if voice_client and voice_client.is_playing():
        voice_client.stop()
        await interaction.response.send_message("⏭ Pulou a música")
    else:
        await interaction.response.send_message("Nada está tocando!")

@bot.tree.command(name="queue", description="Mostra a fila de músicas")
async def show_queue(interaction: discord.Interaction):
    """Mostra as músicas na fila de reprodução"""
    queue = get_queue(interaction.guild.id)
    if not queue.queue and not (interaction.guild.voice_client and interaction.guild.voice_client.is_playing()):
        return await interaction.response.send_message("A fila está vazia!")
    
    message = []
    
    if interaction.guild.voice_client and interaction.guild.voice_client.is_playing():
        current = interaction.guild.voice_client.source
        message.append(f"**Tocando agora:** {current.title}")
    
    if queue.queue:
        message.append("**Próximas músicas:**")
        message.extend(f"{i+1}. {song.title}" for i, song in enumerate(queue.queue[:5]))
    
    await interaction.response.send_message("\n".join(message))

@bot.tree.command(name="pause", description="Pausa a música atual")
async def pause(interaction: discord.Interaction):
    """Pausa a reprodução atual"""
    voice_client = interaction.guild.voice_client
    if voice_client and voice_client.is_playing():
        voice_client.pause()
        await interaction.response.send_message("⏸ Música pausada")
    else:
        await interaction.response.send_message("Nada está tocando!")

@bot.tree.command(name="resume", description="Continua a música pausada")
async def resume(interaction: discord.Interaction):
    """Continua a reprodução pausada"""
    voice_client = interaction.guild.voice_client
    if voice_client and voice_client.is_paused():
        voice_client.resume()
        await interaction.response.send_message("▶ Música continuada")
    else:
        await interaction.response.send_message("Nada está pausado!")

@bot.tree.command(name="stop", description="Para a música e limpa a fila")
async def stop(interaction: discord.Interaction):
    """Para o player e desconecta"""
    voice_client = interaction.guild.voice_client
    if voice_client:
        get_queue(interaction.guild.id).queue.clear()
        await voice_client.disconnect()
        await interaction.response.send_message("🛑 Player parado e desconectado")
    else:
        await interaction.response.send_message("Não estou conectado!")

@bot.tree.command(name="volume", description="Ajusta o volume (0-100)")
@app_commands.describe(level="Nível do volume (0-100)")
async def set_volume(interaction: discord.Interaction, level: int):
    """Ajusta o volume do player"""
    if not 0 <= level <= 100:
        return await interaction.response.send_message("Volume deve estar entre 0 e 100", ephemeral=True)
    
    voice_client = interaction.guild.voice_client
    if voice_client and voice_client.source:
        queue = get_queue(interaction.guild.id)
        queue.volume = level / 100
        voice_client.source.volume = queue.volume
        await interaction.response.send_message(f"🔊 Volume ajustado para {level}%")
    else:
        await interaction.response.send_message("Nada está tocando para ajustar o volume!")

@bot.tree.command(name="loop", description="Ativa/desativa o modo loop")
async def toggle_loop(interaction: discord.Interaction):
    """Ativa ou desativa o loop da música atual"""
    queue = get_queue(interaction.guild.id)
    queue.loop = not queue.loop
    status = "✅ ATIVADO" if queue.loop else "❌ DESATIVADO"
    await interaction.response.send_message(f"🔁 Modo loop: {status}")

@bot.tree.command(name="shuffle", description="Embaralha a fila de músicas")
async def shuffle_queue(interaction: discord.Interaction):
    """Embaralha a ordem das músicas na fila"""
    queue = get_queue(interaction.guild.id)
    if len(queue.queue) > 1:
        # Mantém a música atual se estiver tocando
        if interaction.guild.voice_client and interaction.guild.voice_client.is_playing():
            current = queue.queue.popleft()
            shuffled = list(queue.queue)
            random.shuffle(shuffled)
            queue.queue.clear()
            queue.queue.append(current)
            queue.queue.extend(shuffled)
        else:
            shuffled = list(queue.queue)
            random.shuffle(shuffled)
            queue.queue.clear()
            queue.queue.extend(shuffled)
        await interaction.response.send_message("🔀 Fila embaralhada!")
    else:
        await interaction.response.send_message("Precisa de pelo menos 2 músicas na fila!")

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f'Bot conectado como {bot.user}')
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.listening,
        name="/play | música 🎵"
    ))

if __name__ == "__main__":
    bot.run(TOKEN)
