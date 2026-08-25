import asyncio
import os
import html
import json
import logging
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import BufferedInputFile
from openai import AsyncOpenAI, RateLimitError, AuthenticationError, APIError
from google import genai
from google.genai import types as gemini_types

load_dotenv()

# ✅ შენი ტელეგრამის ტოკენი მყარად ჩასმულია
BOT_TOKEN = "8990693349:AAFqtQk3QoYmWosMTr2FgzFfUv8IKzD_MSI"
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not DEEPSEEK_API_KEY or not GEMINI_API_KEY:
    raise ValueError("კრიტიკული შეცდომა: DEEPSEEK_API_KEY ან GEMINI_API_KEY არ არის მითითებული გარემოს ცვლადებში.")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

deepseek_client = AsyncOpenAI(
    api_key=DEEPSEEK_API_KEY, 
    base_url="https://api.deepseek.com"
)
gemini_client = genai.Client(api_key=GEMINI_API_KEY)

TELEGRAM_MSG_LIMIT = 4096
active_users: set[int] = set()

class TranslationResult(BaseModel):
    final_translation: str = Field(description="საბოლოო დამუშავებული და სრულყოფილი თარგმანი.")
    confidence_score: int = Field(ge=0, le=100, description="სანდოობის ქულა 0-დან 100-მდე.")
    issues_fixed: list[str] = Field(default_factory=list, description="აღმოფხვრილი პრობლემებისა და შესწორებების სია.")
    summary: str = Field(description="მოკლე რეპორტი რა შეიცვალა სინთეზისას.")

async def call_translator(text: str) -> str:
    response = await deepseek_client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {
                "role": "system",
                "content": (
                    "შენ ხარ პროფესიონალი ისტორიული მთარგმნელი. "
                    "თარგმნე მოწოდებული ტექსტი მკაცრად ისტორიულ-დიპლომატიურ სტილში, "
                    "მაქსიმალურად შეინარჩუნე ორიგინალის ტონი და კონტექსტი."
                )
            },
            {"role": "user", "content": text}
        ]
    )
    return response.choices[0].message.content

async def call_accuracy_reviewer(original: str, draft: str) -> str:
    response = await deepseek_client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {
                "role": "system",
                "content": "შენ ხარ სიზუსტის რეცენზენტი (Accuracy Reviewer). შეადარე ორიგინალი და თარგმანი, იპოვე გამოტოვებული, დამატებული ან შეცვლილი დეტალები."
            },
            {"role": "user", "content": f"ორიგინალი:\n{original}\n\nთარგმანის დრაფტი:\n{draft}"}
        ]
    )
    return response.choices[0].message.content

async def call_guard(original: str, draft: str) -> str:
    response = await deepseek_client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {
                "role": "system",
                "content": "შენ ხარ ისტორიული ტერმინოლოგიის მცველი (Guard). შეამოწმე ტექსტი ანაქრონიზმებისა და ეპოქასთან შეუსაბამო ტერმინების კუთხით."
            },
            {"role": "user", "content": f"ორიგინალი კონტექსტი:\n{original}\n\nთარგმანის დრაფტი:\n{draft}"}
        ]
    )
    return response.choices[0].message.content

async def call_critic(original: str, draft: str) -> str:
    response = await deepseek_client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {
                "role": "system",
                "content": "შენ ხარ სტილისტიკის კრიტიკოსი (Critic). შეაფასე ტექსტის მხატვრული და დიპლომატიური ჟღერადობა."
            },
            {"role": "user", "content": f"ორიგინალი:\n{original}\n\nთარგმანის დრაფტი:\n{draft}"}
        ]
    )
    return response.choices[0].message.content

async def call_synthesizer(original: str, draft: str, accuracy_notes: str, guard_notes: str, critic_notes: str) -> TranslationResult:
    prompt = f"""
    [ორიგინალი ტექსტი]:
    {original}

    [საწყისი თარგმანი]:
    {draft}

    [Accuracy Reviewer-ის შენიშვნები]:
    {accuracy_notes}

    [Guard-ის შენიშვნები]:
    {guard_notes}

    [Critic-ის შენიშვნები]:
    {critic_notes}

    გაითვალისწინე ყველა შენიშვნა, გამოასწორე ხარვეზები და ააგე საბოლოო, სრულყოფილი თარგმანი.
    დააბრუნე პასუხი მკაცრად JSON ფორმატში, რომელიც აკმაყოფილებს შემდეგ სტრუქტურას:
    {{
        "final_translation": "...",
        "confidence_score": 95,
        "issues_fixed": ["...", "..."],
        "summary": "..."
    }}
    """
    try:
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(
            None,
            lambda: gemini_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=gemini_types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )
        )
        data = json.loads(response.text)
        return TranslationResult(**data)
    except Exception as e:
        logging.error(f"Gemini Synthesizer error: {e}")
        return TranslationResult(
            final_translation=draft,
            confidence_score=75,
            issues_fixed=["სინთეზის შეცდომა — გამოყენებულია DeepSeek-ის საწყისი დრაფტი."],
            summary="Gemini-მ ვერ მოახერხა სრულყოფილი სინთეზი."
        )

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "გამარჯობა! 👋\nმე ვარ მრავალაგენტიანი ისტორიული მთარგმნელი ბოტი.\n"
        "ვმუშაობ **DeepSeek**-ისა და **Gemini**-ს მძლავრი სავაჭრო ჰიბრიდით! 🚀"
    )

async def send_result(message: types.Message, status_msg: types.Message, result: TranslationResult):
    escaped_translation = html.escape(result.final_translation)
    escaped_summary = html.escape(result.summary)
    issues_list = "\n".join([f"• {html.escape(issue)}" for issue in result.issues_fixed]) or "• ხარვეზები არ დაფიქსირებულა."

    response_text = (
        f"✨ <b>დამუშავებული თარგმანი:</b>\n{escaped_translation}\n\n"
        f"📊 <b>სანდოობა:</b> {result.confidence_score}%\n"
        f"🛠 <b>გასწორებული საკითხები:</b>\n{issues_list}\n\n"
        f"📝 <b>სინთეზის რეპორტი:</b> {escaped_summary}"
    )

    if len(response_text) <= TELEGRAM_MSG_LIMIT:
        try:
            await status_msg.edit_text(response_text)
            return
        except TelegramBadRequest:
            pass

    try:
        await status_msg.edit_text(
            f"✅ თარგმანი დასრულებულია (ტექსტი გრძელია სრულად საჩვენებლად).\n"
            f"📊 <b>სანდოობა:</b> {result.confidence_score}%\n"
            f"📝 <b>რეპორტი:</b> {escaped_summary}"
        )
    except TelegramBadRequest:
        pass

    file_bytes = result.final_translation.encode("utf-8")
    document = BufferedInputFile(file_bytes, filename="historical_translation.txt")
    await message.answer_document(document, caption="სრული თარგმანი ფაილში 👆")

@dp.message(F.text)
async def process_translation_request(message: types.Message):
    user_id = message.from_user.id
    if user_id in active_users:
        await message.reply("⏳ წინა მოთხოვნა მუშავდება. გთხოვთ დაელოდოთ.")
        return

    raw_text = message.text
    if len([w for w in raw_text.split() if w.strip()]) > 500:
        await message.reply("❌ ტექსტი ძალიან გრძელია. გთხოვთ, გამოაგზავნოთ 500 სიტყვაზე ნაკლები.")
        return

    active_users.add(user_id)
    status_msg = await message.reply("⏳ <i>ეტაპი 1/3: DeepSeek Translator ამუშავებს...</i>")

    try:
        await bot.send_chat_action(chat_id=message.chat.id, action="typing")
        draft = await call_translator(raw_text)

        try:
            await status_msg.edit_text("⏳ <i>ეტაპი 2/3: DeepSeek ამოწმებს (Accuracy, Guard, Critic)...</i>")
        except TelegramBadRequest:
            pass

        await bot.send_chat_action(chat_id=message.chat.id, action="typing")
        accuracy_feedback, guard_feedback, critic_feedback = await asyncio.gather(
            call_accuracy_reviewer(raw_text, draft),
            call_guard(raw_text, draft),
            call_critic(raw_text, draft)
        )

        try:
            await status_msg.edit_text("⏳ <i>ეტაპი 3/3: Gemini Synthesizer აჯამებს...</i>")
        except TelegramBadRequest:
            pass

        await bot.send_chat_action(chat_id=message.chat.id, action="typing")
        final_result = await call_synthesizer(raw_text, draft, accuracy_feedback, guard_feedback, critic_feedback)

        await send_result(message, status_msg, final_result)

    except AuthenticationError:
        logging.error("DeepSeek auth failed")
        await status_msg.edit_text("❌ DeepSeek-ის API გასაღები არასწორია.")
    except RateLimitError:
        logging.warning("DeepSeek rate limit hit")
        await status_msg.edit_text("❌ სერვისი გადატვირთულია. სცადეთ მოგვიანებით.")
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        try:
            await status_msg.edit_text("❌ სისტემური შეცდომა მოხდა.")
        except TelegramBadRequest:
            await message.reply("❌ კრიტიკული შეცდომა.")
    finally:
        active_users.discard(user_id)

async def main():
    print("🚀 DeepSeek + Gemini ჰიბრიდი ჩაირთო!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())