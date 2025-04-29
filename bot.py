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

# Verificação do PyNaCL
try:
    import nacl
    NACL_READY = True
except ImportError:
    NACL_READY = False
    print("Aviso: PyNaCL não está instalado. Recursos de voz não funcionarão!")

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

    # ... (outros métodos da classe MusicPlayer permanecem iguais)

# Inicialização do bot
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents)
player = MusicPlayer()

async def sync_commands():
    """Sincroniza os comandos slash globalmente"""
    try:
        await bot.tree.sync()
        print("Comandos slash sincronizados com sucesso!")
    except Exception as e:
        print(f"Erro ao sincronizar comandos: {e}")

@bot.hybrid_command(name="setup", description="Sincroniza os comandos do bot")
@commands.is_owner()
async def setup(ctx):
    """Comando para sincronizar os comandos slash"""
    await ctx.defer()
    await sync_commands()
    await ctx.send("✅ Comandos sincronizados!")

@bot.hybrid_command(name="join", description="Entra no seu canal de voz")
async def join(ctx):
    """Faz o bot entrar no canal de voz"""
    try:
        if not ctx.author.voice:
            return await ctx.send("Você precisa estar em um canal de voz!")
        
        if ctx.voice_client:
            if ctx.voice_client.channel == ctx.author.voice.channel:
                return await ctx.send("Já estou no seu canal!")
            await ctx.voice_client.move_to(ctx.author.voice.channel)
        else:
            await ctx.author.voice.channel.connect()
        
        await ctx.send(f"✅ Conectado ao canal {ctx.author.voice.channel.name}")
    except Exception as e:
        await ctx.send(f"❌ Erro ao conectar: {str(e)}")

# [Outros comandos permanecem iguais... skip, stop, pause, resume, queue, volume, loop, shuffle, now]

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
