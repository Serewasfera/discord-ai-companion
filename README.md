# Discord-ai-companion

### [(Посмотреть демо)](https://files.catbox.moe/l4ij8n.mp4)

Discord бот на основе ИИ для текстового и голосового чата, на базе Discord.py

- Поддержка как текстового общения, так и голосового
- Кастомизация личности и системного промпта
- Подключение сервисов базировано на OpenAI-подобном API.
- Вшита поддержка нового стандарта шифрования от Discord (DAVE E2EE)

## OPUS (важно!)

### Windows
Если у вас нет **opus.dll** (или **libopus.dll**) в PATH, установите его по этой инструкции:  
https://github.com/shardlab/discordrb/wiki/Installing-libopus  
В папку из PATH (к примеру, **System32**), или (рекомендуется) поместите его в корневую папку рядом с **main.py**

### Linux
```
sudo apt-get update
sudo apt-get install libopus0 opus-tools
```
(или аналогичные этим команды)

## Установка

1. Клонируйте репозиторий:  
`git clone https://github.com/Serewasfera/discord-ai-companion.git`

2. Скопируйте **.env.example** в **.env**:
```
copy .env.example (Windows)
cp .env.example .env (Linux)
```

3. Отредактируйте **.env** (для API ключей) и **config.yaml** (конфиг всего)

4. `pip install -r requirements.txt`

6. Запустите через `python main.py`

## Благодарности

Спасибо [XASAPHS121](https://github.com/XASAPHS121) за **davey_compat.py**

## Что я использовал для теста?

**T2T**: DeepSeek v3.2
**TTS**: [Supertonic 2](https://github.com/sameert89/supertonic-tts-openai)
**STT**: [faster-whisper-server](https://github.com/speaches-ai/speaches) (теперь Speaches, модель faster-whisper-medium)
