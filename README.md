# Historical Translation Telegram Bot

ისტორიული ტექსტის თარგმნის ექსპერიმენტი DeepSeek-ითა და Gemini-ით.

## Pipeline

A text message of up to 500 whitespace-separated words is translated by DeepSeek. Three DeepSeek review calls run concurrently (accuracy, historical terminology, style). Gemini synthesizes the draft and notes into a Pydantic-validated JSON result. Long translations are sent as a UTF-8 text attachment.

If synthesis fails, the original draft is returned with a fixed confidence value. Confidence scores are model-generated or fallback constants, not calibrated accuracy measurements. The prompt does not explicitly select a target language; users cannot configure one through a bot command.

## Local setup

```bash
git clone https://github.com/miqelius/TRANSLATE.git
cd TRANSLATE
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

```bash
cp .env.example .env
# Fill all three credentials.
python bot.py
```

| Variable | Purpose |
| --- | --- |
| `BOT_TOKEN` | Required Telegram bot token |
| `DEEPSEEK_API_KEY` | Required; model `deepseek-chat` |
| `GEMINI_API_KEY` | Required; model `gemini-2.5-flash` |

`python-dotenv` loads `.env`. `Procfile` starts `python bot.py` as a worker. One active request per user is tracked in memory.

## Manual check

Send `/start`, then a short source passage. Expect draft/review/synthesis status messages followed by a result. Also try more than 500 words; the bot should reject the input before calling providers.

## Limits

There is no offline/free inference implementation: valid provider credentials and available quota are needed, and API use may cost money. Only text is accepted; no document parsing, OCR or voice transcription is implemented. Request state is not persistent, and there is no global usage budget or automated test suite. Provider output needs human review.

## Credential migration

A token was previously embedded in `bot.py`. The current source reads `BOT_TOKEN` instead. Revoke the old token in BotFather and supply a new token locally; deleting a value from current source does not remove it from Git history.

## Source map

`bot.py`: handlers, provider calls, review pipeline and result formatting. `requirements.txt`: dependencies. `Procfile`: worker entrypoint.

## Verification scope

Documentation was checked against the default-branch source on 2026-11-08. Source inspection and Python syntax checks do not establish a working deployment. External services, credentials, and live data were not exercised.
