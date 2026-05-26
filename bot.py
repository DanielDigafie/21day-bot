import os
import json
import logging
import google.generativeai as genai
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler
)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
COACH_USERNAME = os.environ.get("COACH_USERNAME", "Daniel_21day")

genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel("gemini-1.5-flash")

# ── Conversation states ───────────────────────────────────────────────────────
(
    OB_NAME, OB_STATUS, OB_FIELD, OB_CHALLENGE, OB_GOAL,
    CHATTING
) = range(6)

# ── Persistent storage ────────────────────────────────────────────────────────
DATA_FILE = "user_data.json"

def load_data() -> dict:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE) as f:
            return json.load(f)
    return {}

def save_data(data: dict):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def get_user(user_id: str) -> dict:
    return load_data().get(user_id, {})

def update_user(user_id: str, updates: dict):
    data = load_data()
    if user_id not in data:
        data[user_id] = {}
    data[user_id].update(updates)
    save_data(data)

# ── 21-Day Curriculum ─────────────────────────────────────────────────────────
DAYS = {
    1:  {"title": "Self-Discovery and Purpose",           "part": "Know Yourself"},
    2:  {"title": "Skills and Talents",                   "part": "Know Yourself"},
    3:  {"title": "Discipline and Consistency",           "part": "Know Yourself"},
    4:  {"title": "Emotional Intelligence",               "part": "Know Yourself"},
    5:  {"title": "Personal Branding",                    "part": "Know Yourself"},
    6:  {"title": "Communication",                        "part": "Build Your Toolkit"},
    7:  {"title": "Problem-Solving and Critical Thinking","part": "Build Your Toolkit"},
    8:  {"title": "Time Management",                      "part": "Build Your Toolkit"},
    9:  {"title": "Stress Management",                    "part": "Build Your Toolkit"},
    10: {"title": "Leadership Mindset",                   "part": "Build Your Toolkit"},
    11: {"title": "Curriculum Vitae (CV)",                "part": "Present Yourself"},
    12: {"title": "Cover Letter",                         "part": "Present Yourself"},
    13: {"title": "LinkedIn: Your Digital Identity",      "part": "Present Yourself"},
    14: {"title": "Mastering the Interview",              "part": "Present Yourself"},
    15: {"title": "Networking Skills",                    "part": "Present Yourself"},
    16: {"title": "Email Etiquette",                      "part": "Present Yourself"},
    17: {"title": "Workplace Culture and Etiquette",      "part": "Navigate Your Career"},
    18: {"title": "Job Market",                           "part": "Navigate Your Career"},
    19: {"title": "Employment vs. Entrepreneurship",      "part": "Navigate Your Career"},
    20: {"title": "Project Management",                   "part": "Navigate Your Career"},
    21: {"title": "Financial Literacy",                   "part": "Manage Your Life"},
}

# ── System prompt ─────────────────────────────────────────────────────────────
def build_system_prompt(user: dict, day: int) -> str:
    day_info = DAYS.get(day, {})
    return f"""You are the 21-Day Soft Skills Bootcamp companion bot, created by Daniel — a social entrepreneur and medical doctor from Ethiopia who has trained over 160 youth in soft skills through Bego Sitota Charitable Organization.

USER PROFILE:
- Name: {user.get('name', 'the user')}
- Status: {user.get('status', 'unknown')}
- Field: {user.get('field', 'unknown')}
- Biggest challenge: {user.get('challenge', 'unknown')}
- Goal in 21 days: {user.get('goal', 'unknown')}
- Current: Day {day} — {day_info.get('title', '')} (Part: {day_info.get('part', '')})
- Days completed: {user.get('completed_days', [])}

YOUR ROLE:
You are a warm, practical, and honest coach. You help the trainee PRACTICE the concept of their current day — not just talk about it. Every response must be personal, tailored to this specific user, and action-oriented.

TODAY'S TOPIC — Day {day}: {day_info.get('title', '')}
The trainee has already read Day {day} in their book. Do NOT re-explain everything from scratch. Instead:
1. Ask what resonated with them from their reading
2. Connect the concept directly to THEIR situation using their profile
3. Run the exercise CONVERSATIONALLY — real back-and-forth, not a form
4. Give honest, specific feedback (not just "great job!")
5. Push deeper if answers are shallow — ask follow-up questions
6. Use Ethiopian context, local job market examples, and relatable stories

EXERCISE COMPLETION:
Only mark a day complete when the trainee has:
- Given thoughtful, personal answers (not one-liners)
- Had at least 3-4 meaningful exchanges on the topic
- Shown genuine reflection, not surface-level responses

When the day is genuinely complete, end your message with exactly: [DAY_COMPLETE]

ESCALATION:
If the user needs deeper 1-on-1 support beyond what a bot can provide, include exactly: [SUGGEST_COACHING]

LANGUAGE:
Always respond in the same language the user writes in. Amharic → Amharic. English → English. Mixed → match their tone.

TONE:
- Warm but honest — real feedback, not empty encouragement
- Practical — theory always connected to their real life
- Never preachy — keep it conversational, like a trusted mentor
- Never let shallow answers pass without a follow-up

DO NOT write long paragraphs of theory. Keep responses focused and conversational."""

# ── AI response ───────────────────────────────────────────────────────────────
async def get_ai_response(user: dict, user_message: str, history: list) -> str:
    day = user.get("current_day", 1)
    system = build_system_prompt(user, day)

    # Build conversation history for Gemini
    gemini_history = []
    for msg in history[-20:]:
        role = "user" if msg["role"] == "user" else "model"
        gemini_history.append({"role": role, "parts": [msg["content"]]})

    # Start chat with history
    chat_session = gemini_model.start_chat(history=gemini_history)

    # Prepend system prompt to first message if no history
    full_message = f"{system}\n\n---\n\nUser message: {user_message}" if not gemini_history else user_message

    response = chat_session.send_message(full_message)
    return response.text

# ── Handlers ──────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = str(update.effective_user.id)
    existing = get_user(user_id)

    if existing.get("onboarded"):
        day = existing.get("current_day", 1)
        await update.message.reply_text(
            f"Welcome back, {existing.get('name', 'friend')}! 👋\n\n"
            f"You're on Day {day}: *{DAYS[day]['title']}*\n\n"
            f"Just send me a message and we'll continue.\n"
            f"Type /progress to see your journey so far.",
            parse_mode="Markdown"
        )
        return CHATTING

    await update.message.reply_text(
        "🌟 *Welcome to the 21-Day Soft Skills Bootcamp!*\n\n"
        "I'm your personal practice companion. You have the book — I'm here to help you "
        "go deeper, do the exercises, and make every concept real for YOUR life.\n\n"
        "Let me get to know you first so every conversation is personal to you.\n\n"
        "*What's your name?*",
        parse_mode="Markdown"
    )
    return OB_NAME


async def ob_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = str(update.effective_user.id)
    name = update.message.text.strip()
    update_user(user_id, {"name": name})

    keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton("Student"), KeyboardButton("Fresh Graduate")],
         [KeyboardButton("Working Professional"), KeyboardButton("Job Seeker")]],
        one_time_keyboard=True, resize_keyboard=True
    )
    await update.message.reply_text(
        f"Great to meet you, *{name}*! 😊\n\nWhat best describes you right now?",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    return OB_STATUS


async def ob_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = str(update.effective_user.id)
    update_user(user_id, {"status": update.message.text.strip()})
    await update.message.reply_text(
        "What field are you in or hoping to work in?\n"
        "(e.g. health, business, tech, education, NGO, etc.)"
    )
    return OB_FIELD


async def ob_field(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = str(update.effective_user.id)
    update_user(user_id, {"field": update.message.text.strip()})
    await update.message.reply_text(
        "What's your biggest challenge right now — the one thing you most want to improve?\n"
        "Be honest, there are no wrong answers. 🙏"
    )
    return OB_CHALLENGE


async def ob_challenge(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = str(update.effective_user.id)
    update_user(user_id, {"challenge": update.message.text.strip()})
    await update.message.reply_text(
        "Last question — what do you hope to achieve or change in your life "
        "by the end of these 21 days? Dream big. 🚀"
    )
    return OB_GOAL


async def ob_goal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = str(update.effective_user.id)
    goal = update.message.text.strip()
    update_user(user_id, {
        "goal": goal,
        "onboarded": True,
        "current_day": 1,
        "completed_days": [],
        "history": []
    })
    user = get_user(user_id)

    await update.message.reply_text(
        f"Thank you, *{user['name']}*! 🙌\n\n"
        f"I've got you. Let's make these 21 days count.\n\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"📖 *Day 1: {DAYS[1]['title']}*\n"
        f"Part: {DAYS[1]['part']}\n"
        f"━━━━━━━━━━━━━━━━━\n\n"
        f"Go read Day 1 in your book first. Come back when you're done and tell me: "
        f"*what hit you the most from today's reading?*",
        parse_mode="Markdown"
    )
    return CHATTING


async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = str(update.effective_user.id)
    user_message = update.message.text.strip()
    user = get_user(user_id)

    if not user.get("onboarded"):
        await update.message.reply_text("Type /start to begin your journey.")
        return CHATTING

    await update.message.chat.send_action("typing")

    history = user.get("history", [])

    try:
        ai_reply = await get_ai_response(user, user_message, history)
    except Exception as e:
        logger.error(f"AI error: {e}")
        await update.message.reply_text("Sorry, I had a technical issue. Please try again in a moment.")
        return CHATTING

    day_complete    = "[DAY_COMPLETE]" in ai_reply
    suggest_coaching = "[SUGGEST_COACHING]" in ai_reply
    clean_reply     = ai_reply.replace("[DAY_COMPLETE]", "").replace("[SUGGEST_COACHING]", "").strip()

    # Save history
    history.append({"role": "user",      "content": user_message})
    history.append({"role": "assistant", "content": clean_reply})
    update_user(user_id, {"history": history[-40:]})

    await update.message.reply_text(clean_reply)

    # Day completion
    if day_complete:
        current_day = user.get("current_day", 1)
        completed   = user.get("completed_days", [])
        if current_day not in completed:
            completed.append(current_day)

        if current_day < 21:
            next_day = current_day + 1
            update_user(user_id, {
                "current_day": next_day,
                "completed_days": completed,
                "history": []
            })
            await update.message.reply_text(
                f"✅ *Day {current_day} Complete!*\n\n"
                f"You've done real work today. That takes courage.\n\n"
                f"━━━━━━━━━━━━━━━━━\n"
                f"📖 *Day {next_day}: {DAYS[next_day]['title']}*\n"
                f"Part: {DAYS[next_day]['part']}\n"
                f"━━━━━━━━━━━━━━━━━\n\n"
                f"Read Day {next_day} in your book first, then come back. 💪",
                parse_mode="Markdown"
            )
        else:
            update_user(user_id, {"completed_days": completed, "all_complete": True})
            await update.message.reply_text(
                f"🎉 *You've completed all 21 Days!*\n\n"
                f"*{user.get('name', 'Friend')}*, this is a huge achievement.\n\n"
                f"The real journey starts now — applying everything you've learned.\n\n"
                f"For deeper support and 1-on-1 coaching:\n"
                f"👉 @{COACH_USERNAME}",
                parse_mode="Markdown"
            )

    # Coaching escalation
    if suggest_coaching:
        await update.message.reply_text(
            f"💬 *Need deeper support?*\n\n"
            f"Daniel offers 1-on-1 coaching for exactly this kind of situation.\n\n"
            f"👉 Reach out: @{COACH_USERNAME}",
            parse_mode="Markdown"
        )

    return CHATTING


async def progress(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = str(update.effective_user.id)
    user    = get_user(user_id)

    if not user.get("onboarded"):
        await update.message.reply_text("Type /start to begin your journey.")
        return CHATTING

    completed = user.get("completed_days", [])
    current   = user.get("current_day", 1)

    bar = ""
    for d in range(1, 22):
        if d in completed:   bar += "🟢"
        elif d == current:   bar += "🔵"
        else:                bar += "⚪"

    await update.message.reply_text(
        f"📊 *Your 21-Day Journey*\n\n"
        f"{bar}\n\n"
        f"✅ Completed: {len(completed)}/21 days\n"
        f"🔵 Currently on: Day {current} — {DAYS[current]['title']}\n\n"
        f"Keep going, *{user.get('name', 'friend')}*! 💪",
        parse_mode="Markdown"
    )
    return CHATTING


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "🤖 *21-Day Bootcamp Bot — Help*\n\n"
        "/start — Start or resume your journey\n"
        "/progress — See how far you've come\n"
        "/help — Show this message\n\n"
        f"Need human support? Reach out to Daniel: @{COACH_USERNAME}",
        parse_mode="Markdown"
    )
    return CHATTING


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            OB_NAME:      [MessageHandler(filters.TEXT & ~filters.COMMAND, ob_name)],
            OB_STATUS:    [MessageHandler(filters.TEXT & ~filters.COMMAND, ob_status)],
            OB_FIELD:     [MessageHandler(filters.TEXT & ~filters.COMMAND, ob_field)],
            OB_CHALLENGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ob_challenge)],
            OB_GOAL:      [MessageHandler(filters.TEXT & ~filters.COMMAND, ob_goal)],
            CHATTING:     [MessageHandler(filters.TEXT & ~filters.COMMAND, chat)],
        },
        fallbacks=[
            CommandHandler("start",    start),
            CommandHandler("progress", progress),
            CommandHandler("help",     help_command),
        ],
        allow_reentry=True,
        per_message=False,
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("progress", progress))
    app.add_handler(CommandHandler("help",     help_command))

    logger.info("Bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
