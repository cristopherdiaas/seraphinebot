import os
import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp as youtube_dl
import asyncio
from collections import deque
import random
from dotenv import load_dotenv

# Configurações iniciais
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

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

class MusicBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.voice_states = True
        
        super().__init__(
            command_prefix='!',
            intents=intents
        )
        
        self.queues = {}
        self.loops = {}
        self.volumes = {}
        self.default_volume = 0.5

    async def setup_hook(self):
        # Sincroniza os comandos slash
        await self.tree.sync()
        print("Comandos slash sincronizados!")

    async def get_info(self, query):
        with youtube_dl.YoutubeDL(YTDL_OPTIONS) as ydl:
            info = ydl.extract_info(f"ytsearch:{query}" if not query.startswith('http') else query, download=False)
            return info['entries'][0] if 'entries' in info else info

    async def create_source(self, info, volume=0.5):
        return discord.FFmpegPCMAudio(info['url'], **FFMPEG_OPTIONS)

    def get_queue(self, guild_id):
        if guild_id not in self.queues:
            self.queues[guild_id] = deque(maxlen=50)
        return self.queues[guild_id]

    async def play_next(self, interaction):
        queue = self.get_queue(interaction.guild.id)
        
        if self.loops.get(interaction.guild.id, False) and queue:
            await self.play_song(interaction, queue[0])
            return

        if queue:
            next_song = queue.popleft()
            await self.play_song(interaction, next_song)

    async def play_song(self, interaction, song):
        try:
            interaction.guild.voice_client.play(
                song['audio'],
                after=lambda e: asyncio.run_coroutine_threadsafe(
                    self.play_next(interaction), 
                    self.loop
                )
            )
            await interaction.followup.send(f"🎵 Tocando agora: **{song['title']}**")
        except Exception as e:
            await interaction.followup.send(f"❌ Erro ao reproduzir: {str(e)}")
            await self.play_next(interaction)

bot = MusicBot()

@bot.tree.command(name="play", description="Toca uma música do YouTube")
@app_commands.describe(query="URL ou nome da música")
async def play(interaction: discord.Interaction, query: str):
    """Toca música a partir de uma URL ou busca"""
    await interaction.response.defer()
    
    if not interaction.user.voice:
        return await interaction.followup.send("Você precisa estar em um canal de voz!")
    
    try:
        # Conectar ao canal de voz se necessário
        if not interaction.guild.voice_client:
            await interaction.user.voice.channel.connect()
        elif interaction.guild.voice_client.channel != interaction.user.voice.channel:
            return await interaction.followup.send("Estou em outro canal de voz!")

        info = await bot.get_info(query)
        if not info:
            return await interaction.followup.send("Não encontrei essa música.")
        
        volume = bot.volumes.get(interaction.guild.id, bot.default_volume)
        source = await bot.create_source(info, volume)
        
        song_data = {
            'audio': source,
            'title': info['title'],
            'url': info['webpage_url']
        }
        
        queue = bot.get_queue(interaction.guild.id)
        
        if interaction.guild.voice_client.is_playing():
            queue.append(song_data)
            return await interaction.followup.send(f"🎶 Adicionado à fila (#{len(queue)}): **{info['title']}**")
        
        queue.append(song_data)
        await bot.play_song(interaction, song_data)
        
    except Exception as e:
        await interaction.followup.send(f"⚠️ Erro: {str(e)}")

@bot.tree.command(name="skip", description="Pula a música atual")
async def skip(interaction: discord.Interaction):
    """Pula para a próxima música"""
    if interaction.guild.voice_client and interaction.guild.voice_client.is_playing():
        interaction.guild.voice_client.stop()
        await interaction.response.send_message("⏭ Pulou a música")
    else:
        await interaction.response.send_message("Nada está tocando!")

@bot.tree.command(name="stop", description="Para a música e limpa a fila")
async def stop(interaction: discord.Interaction):
    """Para o player e desconecta"""
    if interaction.guild.voice_client:
        bot.get_queue(interaction.guild.id).clear()
        await interaction.guild.voice_client.disconnect()
        await interaction.response.send_message("🛑 Player parado e desconectado")
    else:
        await interaction.response.send_message("Não estou conectado!")

@bot.tree.command(name="queue", description="Mostra a fila de músicas")
async def queue(interaction: discord.Interaction):
    """Mostra as próximas músicas na fila"""
    queue = bot.get_queue(interaction.guild.id)
    
    if not queue and not (interaction.guild.voice_client and interaction.guild.voice_client.is_playing()):
        return await interaction.response.send_message("A fila está vazia!")
    
    message = []
    
    if interaction.guild.voice_client and interaction.guild.voice_client.is_playing():
        message.append("**Tocando agora:** Música atual")
    
    if queue:
        message.append("**Próximas músicas:**")
        message.extend(f"{i+1}. {song['title']}" for i, song in enumerate(queue[:5]))
    
    await interaction.response.send_message("\n".join(message))

@bot.event
async def on_ready():
    print(f'Bot conectado como {bot.user}')
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.listening,
        name="música 🎵"
    ))

if __name__ == "__main__":
    bot.run(TOKEN)
