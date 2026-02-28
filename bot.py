import os
import json
import asyncio
import logging
from dotenv import load_dotenv
# pyright: reportPrivateImportUsage=false
import google.generativeai as genai
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# =========================
# CONFIG
# =========================

load_dotenv()

from typing import cast

load_dotenv()

TELEGRAM_TOKEN = cast(str, os.getenv("TELEGRAM_TOKEN"))
GEMINI_API_KEY = cast(str, os.getenv("GEMINI_API_KEY"))

if not TELEGRAM_TOKEN:
    raise ValueError("Missing TELEGRAM_TOKEN")
if not GEMINI_API_KEY:
    raise ValueError("Missing GEMINI_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

# =========================
# LOGGING
# =========================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# =========================
# MEMORY STORAGE
# =========================

user_sessions = {}
user_scores = {}

# =========================
# COMMANDS
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return
    await update.message.reply_text(
        "Welcome to SAT Math Bot 🚀\n\n"
        "Type /problem to get a new SAT-style question."
    )

# =========================
# AI PROBLEM GENERATION
# =========================

async def generate_problem():
    prompt = """
Generate one SAT-style algebra problem.

Return ONLY valid JSON in this format:

{
  "question": "...",
  "choices": {
    "A": "...",
    "B": "...",
    "C": "...",
    "D": "..."
  },
  "correct_answer": "A",
  "explanation": "step-by-step explanation"
}

No markdown. No backticks. Only JSON.
Difficulty: Medium.
"""

    try:
        loop = asyncio.get_running_loop()

        # Run Gemini in thread pool (prevents bot freezing)
        response = await loop.run_in_executor(
            None,
            lambda: model.generate_content(prompt)
        )

        text = response.text.strip()
        text = text.replace("```json", "").replace("```", "").strip()

        data = json.loads(text)

        # Validate structure
        required_keys = ["question", "choices", "correct_answer", "explanation"]
        if not all(key in data for key in required_keys):
            raise ValueError("Invalid JSON structure")

        return data

    except Exception as e:
        logger.error(f"Gemini Error: {e}")

        # Fallback question
        return {
            "question": "If 2x + 3 = 11, what is x?",
            "choices": {
                "A": "3",
                "B": "4",
                "C": "5",
                "D": "6"
            },
            "correct_answer": "B",
            "explanation": "2x + 3 = 11 → 2x = 8 → x = 4"
        }

# =========================
# /problem COMMAND
# =========================

async def problem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None or update.effective_user is None:
        return

    user_id = update.effective_user.id

    # Prevent multiple active problems
    if user_id in user_sessions:
        await update.message.reply_text(
            "You already have a question. Answer it first!"
        )
        return

    await update.message.chat.send_action("typing")

    data = await generate_problem()

    user_sessions[user_id] = data

    question_text = data["question"]
    choices = data["choices"]

    formatted = f"{question_text}\n\n"
    for key, value in choices.items():
        formatted += f"{key}) {value}\n"

    formatted += "\n📝 Reply with A, B, C, or D."

    await update.message.reply_text(formatted)

# =========================
# ANSWER CHECKING
# =========================

async def check_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None or update.effective_user is None:
        return

    if update.message.text is None:
        return

    user_id = update.effective_user.id
    user_answer = update.message.text.strip().upper()

    if user_id not in user_sessions:
        return

    if user_answer not in ["A", "B", "C", "D"]:
        await update.message.reply_text("Please reply with A, B, C, or D.")
        return

    data = user_sessions[user_id]
    correct = data["correct_answer"]

    # Initialize score if not exists
    if user_id not in user_scores:
        user_scores[user_id] = {"correct": 0, "total": 0}

    user_scores[user_id]["total"] += 1

    if user_answer == correct:
        user_scores[user_id]["correct"] += 1
        reply = "✅ Correct!\n\n"
    else:
        reply = f"❌ Incorrect.\nCorrect answer: {correct}\n\n"

    reply += "Explanation:\n" + data["explanation"]

    score = user_scores[user_id]
    reply += f"\n\n📊 Your Score: {score['correct']}/{score['total']}"

    await update.message.reply_text(reply)

    # Clear active question
    del user_sessions[user_id]

# =========================
# MAIN
# =========================

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("problem", problem))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, check_answer))

    logger.info("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()