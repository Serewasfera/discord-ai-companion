import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=== dave.py ===")
import dave
print(f"  Max protocol version: {dave.get_max_supported_protocol_version()}")
print(f"  Has Session: {hasattr(dave, 'Session')}")
print(f"  Has Encryptor: {hasattr(dave, 'Encryptor')}")

print("\n=== davey_compat ===")
import davey_compat
print(f"  DAVE_PROTOCOL_VERSION: {davey_compat.DAVE_PROTOCOL_VERSION}")
print(f"  Has DaveSession: {hasattr(davey_compat, 'DaveSession')}")
print(f"  Has CommitWelcome: {hasattr(davey_compat, 'CommitWelcome')}")

print("\n=== discord.py shim ===")
import discord.voice_state
import discord.gateway
discord.voice_state.davey = davey_compat
discord.gateway.davey = davey_compat
davey_compat.patch_reinit(discord.voice_state)
print(f"  voice_state.davey: {discord.voice_state.davey}")
print(f"  gateway.davey: {discord.gateway.davey}")

print("\n=== Готово ✅ ===")