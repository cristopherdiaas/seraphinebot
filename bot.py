import os
import discord
from discord.ext import commands
import yt_dlp as youtube_dl
import asyncio
from collections import deque
import random
from dotenv import load_dotenv

# Configurações
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
PREFIX = os.getenv('PREFIX', '!')

# Configurações do yt-dlp
YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'extractaudio': True,
    'noplaylist': True,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

class MusicPlayer:
    def __init__(self):
        self.queues = {}
        self.loops = {}
        self.volumes = {}
        self.default_volume = 0.5

    def get_queue(self, guild_id):
        if guild_id not in self.queues:
            self.queues[guild_id] = deque(maxlen=50)  # Limite de 50 músicas
        return self.queues[guild_id]

    async def play_next(self, ctx):
        queue = self.get_queue(ctx.guild.id)
        
        if self.loops.get(ctx.guild.id, False) and queue:
            # Modo loop - toca a mesma música novamente
            await self.play_source(ctx, queue[0])
            return

        if queue:
            next_song = queue.popleft()
            await self.play_source(ctx, next_song)

    async def play_source(self, ctx, source):
        try:
            ctx.voice_client.play(
                source['audio'],
                after=lambda e: asyncio.run_coroutine_threadsafe(self.play_next(ctx), bot.loop)
            )
            await ctx.send(f"🎵 **Tocando agora:** {source['title']}")
        except Exception as e:
            await ctx.send(f"❌ Erro ao reproduzir: {str(e)}")
            await self.play_next(ctx)

    async def create_source(self, info, volume=0.5):
        audio_source = discord.FFmpegPCMAudio(info['url'], **FFMPEG_OPTIONS)
        return {
            'audio': audio_source,
            'title': info['title'],
            'url': info['webpage_url'],
            'duration': info.get('duration', 0),
            'volume': volume
        }

    async def get_info(self, query):
        with youtube_dl.YoutubeDL(YTDL_OPTIONS) as ydl:
            info = ydl.extract_info(f"ytsearch:{query}" if not query.startswith('http') else query, download=False)
            if 'entries' in info:
                info = info['entries'][0]
            return info

# Inicialização do bot
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents)
player = MusicPlayer()

@bot.hybrid_command(name="play", description="Toca uma música ou adiciona à fila")
async def play(ctx, *, query: str):
    """Toca música do YouTube (URL ou nome)"""
    await ctx.defer()
    
    # Verificação de canal de voz
    if not ctx.author.voice:
        return await ctx.send("Entre em um canal de voz primeiro!")
    
    if not ctx.voice_client:
        await ctx.author.voice.channel.connect()
    elif ctx.voice_client.channel != ctx.author.voice.channel:
        return await ctx.send("Estou em outro canal de voz!")

    try:
        info = await player.get_info(query)
        if not info:
            return await ctx.send("Não encontrei essa música.")
        
        volume = player.volumes.get(ctx.guild.id, player.default_volume)
        source = await player.create_source(info, volume)
        queue = player.get_queue(ctx.guild.id)
        
        if ctx.voice_client.is_playing() or ctx.voice_client.is_paused():
            queue.append(source)
            return await ctx.send(f"🎶 Adicionado à fila (#{len(queue)}): **{info['title']}**")
        
        queue.append(source)  # Adiciona à fila mesmo que esteja vazia
        await player.play_next(ctx)
        
    except Exception as e:
        await ctx.send(f"⚠️ Erro: {str(e)}")

@bot.hybrid_command(name="skip", description="Pula a música atual")
async def skip(ctx):
    """Pula para a próxima música"""
    if ctx.voice_client and (ctx.voice_client.is_playing() or ctx.voice_client.is_paused()):
        ctx.voice_client.stop()
        await ctx.send("⏭ Pulou para a próxima música")
    else:
        await ctx.send("Nada está tocando!")

@bot.hybrid_command(name="stop", description="Para a música e limpa a fila")
async def stop(ctx):
    """Para o player e desconecta"""
    if ctx.voice_client:
        player.get_queue(ctx.guild.id).clear()
        await ctx.voice_client.disconnect()
        await ctx.send("🛑 Player parado e desconectado")
    else:
        await ctx.send("Não estou conectado!")

@bot.hybrid_command(name="pause", description="Pausa a música atual")
async def pause(ctx):
    """Pausa a reprodução"""
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("⏸ Música pausada")
    else:
        await ctx.send("Nada está tocando!")

@bot.hybrid_command(name="resume", description="Continua a música pausada")
async def resume(ctx):
    """Continua a reprodução"""
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("▶ Música continuada")
    else:
        await ctx.send("Nada está pausado!")

@bot.hybrid_command(name="queue", description="Mostra a fila atual")
async def show_queue(ctx):
    """Mostra as próximas músicas"""
    queue = player.get_queue(ctx.guild.id)
    if not queue:
        return await ctx.send("A fila está vazia!")
    
    current = "Tocando agora: " + (
        ctx.voice_client.source.title if hasattr(ctx.voice_client.source, 'title') 
        else "Música atual"
    )
    
    upcoming = "\n".join(
        f"{i+1}. {song['title']}" 
        for i, song in enumerate(list(queue)[:10])
    )
    
    await ctx.send(f"**🎶 Fila de reprodução**\n{current}\n\n**Próximas:**\n{upcoming}")

@bot.hybrid_command(name="volume", description="Ajusta o volume (0-100)")
async def volume(ctx, level: int):
    """Ajusta o volume (0-100)"""
    if not 0 <= level <= 100:
        return await ctx.send("Volume deve estar entre 0 e 100")
    
    player.volumes[ctx.guild.id] = level / 100
    await ctx.send(f"🔊 Volume ajustado para {level}%")

@bot.hybrid_command(name="loop", description="Ativa/desativa o modo loop")
async def loop(ctx):
    """Repete a música atual continuamente"""
    player.loops[ctx.guild.id] = not player.loops.get(ctx.guild.id, False)
    status = "✅ ATIVADO" if player.loops[ctx.guild.id] else "❌ DESATIVADO"
    await ctx.send(f"🔁 Modo loop: {status}")

@bot.hybrid_command(name="shuffle", description="Embaralha a fila")
async def shuffle(ctx):
    """Embaralha a ordem da fila"""
    queue = player.get_queue(ctx.guild.id)
    if len(queue) > 1:
        # Mantém a música atual se estiver tocando
        if ctx.voice_client and ctx.voice_client.is_playing():
            current = queue.popleft()
            shuffled = list(queue)
            random.shuffle(shuffled)
            queue.clear()
            queue.append(current)
            queue.extend(shuffled)
        else:
            shuffled = list(queue)
            random.shuffle(shuffled)
            queue.clear()
            queue.extend(shuffled)
        await ctx.send("🔀 Fila embaralhada!")
    else:
        await ctx.send("Precisa de pelo menos 2 músicas na fila!")

@bot.hybrid_command(name="now", description="Mostra a música atual")
async def now_playing(ctx):
    """Mostra informações da música atual"""
    if ctx.voice_client and ctx.voice_client.is_playing():
        if hasattr(ctx.voice_client.source, 'title'):
            await ctx.send(f"🎵 Tocando agora: **{ctx.voice_client.source.title}**")
        else:
            await ctx.send("🎵 Tocando música (informações não disponíveis)")
    else:
        await ctx.send("Nada está tocando no momento!")

@bot.event
async def on_ready():
    print(f'Bot conectado como {bot.user}')
    await bot.tree.sync()
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.listening,
        name=f"{PREFIX}help | música 🎵"
    ))

if __name__ == "__main__":
    bot.run(TOKEN)
