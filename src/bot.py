import asyncio
import discord
from discord.ext import commands
from discord.ext import voice_recv

from .config import AppConfig
from .llm import LLMClient
from .stt import STTClient
from .tts import TTSClient
from .voice import VoiceSession


def create_bot(cfg: AppConfig) -> commands.Bot:
    intents = discord.Intents.default()
    intents.message_content = True
    intents.voice_states = True
    intents.guilds = True
    intents.members = True

    bot = commands.Bot(command_prefix=cfg.discord.command_prefix, intents=intents)

    llm = LLMClient(cfg.llm, cfg.persona)
    stt = STTClient(cfg.stt)
    tts = TTSClient(cfg.tts)

    voice_sessions: dict[int, VoiceSession] = {}

    @bot.event
    async def on_ready():
        print(f"✅ Залогинились как {bot.user} ({bot.user.id})")
        guild = bot.get_guild(cfg.discord.guild_id)
        print(f"   Сервер: {guild.name if guild else 'НЕ НАЙДЕН'}")

    @bot.event
    async def on_message(message: discord.Message):
        if message.author.bot:
            return
        if message.guild and message.guild.id != cfg.discord.guild_id:
            return

        await bot.process_commands(message)
        if message.content.startswith(cfg.discord.command_prefix):
            return

        is_main_channel = (
            cfg.discord.respond_in_main_channel
            and message.channel.id == cfg.discord.main_channel_id
        )
        is_mention = (
            cfg.discord.respond_to_mentions and bot.user in message.mentions
        )
        is_dm = isinstance(message.channel, discord.DMChannel)

        if not (is_main_channel or is_mention or is_dm):
            return

        text = message.clean_content.strip()
        if not text:
            return

        async with message.channel.typing():
            try:
                key = f"text:{message.channel.id}"
                answer = await llm.chat(key, f"{message.author.display_name}: {text}")
                await message.reply(answer, mention_author=False)
            except Exception as e:
                await message.reply(f"⚠️ Ошибка: {e}")

    @bot.command(name="join", help="Зайти в твой голосовой канал")
    async def join(ctx: commands.Context):
        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.reply("Зайди сначала в голосовой канал 🙃")
            return

        channel = ctx.author.voice.channel

        if ctx.voice_client:
            try:
                await ctx.voice_client.disconnect(force=True)
            except Exception:
                pass
            await asyncio.sleep(1.0)

        try:
            vc = await channel.connect(
                cls=voice_recv.VoiceRecvClient,
                timeout=30.0,
                reconnect=True,
                self_deaf=False,
            )
        except Exception as e:
            await ctx.reply(f"❌ Ошибка подключения: {type(e).__name__}: {e}")
            return

        # Ждём готовности UDP-сессии
        for _ in range(60):
            if vc.is_connected():
                break
            await asyncio.sleep(0.1)
        else:
            await ctx.reply("⚠️ Voice не готов")
            await vc.disconnect(force=True)
            return

        # Запас на DAVE/MLS handshake
        await asyncio.sleep(1.0)

        text_channel = bot.get_channel(cfg.discord.main_channel_id)
        session = VoiceSession(vc, llm, stt, tts, cfg.voice, text_channel)

        try:
            session.start()
        except Exception as e:
            await ctx.reply(f"⚠️ Не удалось начать запись: {e}")
            import traceback; traceback.print_exc()
            await vc.disconnect(force=True)
            return

        voice_sessions[ctx.guild.id] = session
        await ctx.reply(f"🎧 Зашла в **{channel.name}**, слушаю!")

    @bot.command(name="leave", help="Выйти из голосового канала")
    async def leave(ctx: commands.Context):
        session = voice_sessions.pop(ctx.guild.id, None)
        if session:
            session.stop()
        if ctx.voice_client:
            await ctx.voice_client.disconnect(force=False)
            await ctx.reply("👋 Вышел")
        else:
            await ctx.reply("Я не в голосовом канале")

    @bot.command(name="reset", help="Сбросить историю в текущем канале")
    async def reset(ctx: commands.Context):
        llm.reset(f"text:{ctx.channel.id}")
        await ctx.reply("🧹 История очищена")

    @bot.command(name="dave_status", help="Показать статус DAVE-сессии")
    async def dave_status(ctx: commands.Context):
        if not ctx.voice_client:
            await ctx.reply("Не в голосовом канале")
            return

        state = getattr(ctx.voice_client, "_connection", None)
        ds = getattr(state, "dave_session", None) if state else None

        if ds is None:
            await ctx.reply("DAVE session не найдена")
            return

        info = (
            f"**DAVE статус:**\n"
            f"• ready: `{ds.ready}`\n"
            f"• status: `{ds.status}`\n"
            f"• epoch: `{ds.epoch}`\n"
            f"• repr: `{ds!r}`"
        )
        await ctx.reply(info)

    return bot