import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import davey_compat
import discord.voice_state
import discord.gateway

discord.voice_state.davey = davey_compat
discord.gateway.davey = davey_compat
davey_compat.patch_reinit(discord.voice_state)

import voice_recv_dave_patch
voice_recv_dave_patch.apply_dave_patch()

print("✅ DAVE shim + voice_recv patch готовы")

import discord
if not discord.opus.is_loaded():
    try:
        import opuslib
        dll_path = os.path.join(os.path.dirname(opuslib.__file__), "opus.dll")
        discord.opus.load_opus(dll_path)
    except (ImportError, OSError):
        for name in ("opus", "libopus-0", "libopus.so.0"):
            try:
                discord.opus.load_opus(name)
                break
            except OSError:
                continue

if not discord.opus.is_loaded():
    print("❌ Opus не загружен")
    sys.exit(1)

print("✅ Opus загружен")

import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
"""
logging.getLogger("discord.http").setLevel(logging.WARNING)
logging.getLogger("discord.gateway").setLevel(logging.WARNING)
logging.getLogger("discord.ext.voice_recv").setLevel(logging.DEBUG)
logging.getLogger("discord.ext.voice_recv").setLevel(logging.DEBUG)
"""

from src.config import load_config
from src.bot import create_bot


def main():
    cfg = load_config("config.yaml")
    bot = create_bot(cfg)
    try:
        bot.run(cfg.discord.token)
    finally:
        pass


if __name__ == "__main__":
    main()