import os
from dataclasses import dataclass
from pathlib import Path
import yaml
from dotenv import load_dotenv

load_dotenv()


@dataclass
class DiscordCfg:
    token: str
    guild_id: int
    main_channel_id: int
    command_prefix: str
    respond_to_mentions: bool
    respond_in_main_channel: bool


@dataclass
class LLMCfg:
    base_url: str
    api_key: str
    model: str
    temperature: float
    top_p: float
    frequency_penalty: float
    presence_penalty: float
    max_tokens: int
    history_size: int
    history_dir: str


@dataclass
class STTCfg:
    base_url: str
    api_key: str
    model: str
    language: str


@dataclass
class TTSCfg:
    base_url: str
    api_key: str
    model: str
    voice: str
    response_format: str
    speed: float


@dataclass
class PersonaCfg:
    system_prompt: str
    personality: str
    bot_name: str


@dataclass
class VoiceCfg:
    silence_threshold_ms: int
    min_audio_length_ms: int
    sample_rate: int


@dataclass
class AppConfig:
    discord: DiscordCfg
    llm: LLMCfg
    stt: STTCfg
    tts: TTSCfg
    persona: PersonaCfg
    voice: VoiceCfg


def _read_file(path: str) -> str:
    return Path(path).read_text(encoding="utf-8").strip()


def load_config(path: str = "config.yaml") -> AppConfig:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    d = raw["discord"]
    l = raw["llm"]
    s = raw["stt"]
    t = raw["tts"]
    p = raw["persona"]
    v = raw["voice"]

    persona = PersonaCfg(
        system_prompt=_read_file(p["system_prompt_file"]),
        personality=_read_file(p["personality_file"]),
        bot_name=p["bot_name"],
    )

    return AppConfig(
        discord=DiscordCfg(
            token=os.environ["DISCORD_TOKEN"],
            guild_id=int(d["guild_id"]),
            main_channel_id=int(d["main_channel_id"]),
            command_prefix=d.get("command_prefix", "!"),
            respond_to_mentions=d.get("respond_to_mentions", True),
            respond_in_main_channel=d.get("respond_in_main_channel", True),
        ),
        llm=LLMCfg(
            base_url=l["base_url"],
            api_key=os.environ[l["api_key_env"]],
            model=l["model"],
            temperature=l.get("temperature", 0.8),
            top_p=l.get("top_p", 0.95),
            frequency_penalty=l.get("frequency_penalty", 0.0),
            presence_penalty=l.get("presence_penalty", 0.0),
            max_tokens=l.get("max_tokens", 800),
            history_size=l.get("history_size", 20),
            history_dir=l.get("history_dir", "data/history"),
        ),
        stt=STTCfg(
            base_url=s["base_url"],
            api_key=os.environ[s["api_key_env"]],
            model=s["model"],
            language=s.get("language", "ru"),
        ),
        tts=TTSCfg(
            base_url=t["base_url"],
            api_key=os.environ[t["api_key_env"]],
            model=t["model"],
            voice=t["voice"],
            response_format=t.get("response_format", "opus"),
            speed=t.get("speed", 1.0),
        ),
        persona=persona,
        voice=VoiceCfg(
            silence_threshold_ms=v.get("silence_threshold_ms", 800),
            min_audio_length_ms=v.get("min_audio_length_ms", 400),
            sample_rate=v.get("sample_rate", 48000),
        ),
    )