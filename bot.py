import os
import logging
import json
from datetime import datetime
import redis
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from telegram.constants import ParseMode
from telegram.helpers import escape_markdown
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot token
BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    raise ValueError("Please set BOT_TOKEN environment variable")

# Redis setup for persistent storage
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
r = redis.Redis.from_url(REDIS_URL, decode_responses=True)

# ----------------- Utility Functions -----------------

def save_user_notes(user_id, notes):
    """Save user notes to Redis"""
    r.set(f"user_notes:{user_id}", json.dumps(notes))

def load_user_notes(user_id):
    """Load user notes from Redis"""
    data = r.get(f"user_notes:{user_id}")
    return json.loads(data) if data else []

def get_user_notes(user_id):
    return load_user_notes(user_id)

def add_user_note(user_id, title, content, category="General"):
    notes = get_user_notes(user_id)
    note_id = len(notes) + 1
    note = {
        "note_id": note_id,
        "title": title,
        "content": content,
        "category": category,
        "created_at": datetime.now().isoformat()
    }
    notes.append(note)
    save_user_notes(user_id, notes)
    return note_id

def delete_user_note(user_id, note_id):
    notes = get_user_notes(user_id)
    new_notes = [n for n in notes if n["note_id"] != note_id]
    save_user_notes(user_id, new_notes)
    return len(new_notes) != len(notes)

def get_user_note(user_id, note_id):
    notes = get_user_notes(user_id)
    for n in notes:
        if n["note_id"] == note_id:
            return n
    return None

def search_user_notes(user_id, query):
    notes = get_user_notes(user_id)
    query = query.lower()
    return [n for n in notes if query in n["title"].lower() or query in n["content"].lower() or query in n["category"].lower()]

def get_user_categories(user_id):
    notes = get_user_notes(user_id)
    return sorted(list(set(n["category"] for n in notes)))

# ----------------- Bot Handlers -----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    welcome_text = f"""
👋 *Hello {escape_markdown(user.first_name, version=2)}!* Welcome to Notepad++ Bot! 📝

✨ *Features:*
• 📝 Create and save notes with titles
• 📋 View and organize notes by categories
• 🔍 Search through your notes
• 🗂️ Categorize your notes
• ⚡ Quick inline navigation
• 🗑️ Delete notes
"""
    keyboard = [
        [InlineKeyboardButton("➕ New Note", callback_data='new_note')],
        [InlineKeyboardButton("📋 My Notes", callback_data='view_notes')],
        [InlineKeyboardButton("🔍 Search Notes", callback_data='search_notes')],
        [InlineKeyboardButton("🗂️ Categories", callback_data='view_categories')],
        [InlineKeyboardButton("📊 Statistics", callback_data='stats')],
        [InlineKeyboardButton("❓ Help Guide", callback_data='help')]
    ]
    await update.message.reply_text(welcome_text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=InlineKeyboardMarkup(keyboard))

async def new_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['awaiting_note'] = True
    await update.message.reply_text(
        "📝 *Let's create a new note!*\n\nSend me the note text. You can format:\n"
        "*Title:* Your Title\\n*Content:* Your content\n\n"
        "Or just send content for auto-title.",
        parse_mode=ParseMode.MARKDOWN_V2
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        text = update.message.text

        if context.user_data.get('awaiting_note'):
            title, content = None, text
            if text.lower().startswith("title:"):
                lines = text.split("\n")
                for line in lines:
                    if line.lower().startswith("title:"):
                        title = line.split(":",1)[1].strip()
                    elif line.lower().startswith("content:"):
                        content = line.split(":",1)[1].strip()
            if not title:
                title = content[:30] + ("..." if len(content) > 30 else "")
            note_id = add_user_note(user_id, title, content)
            keyboard = [
                [InlineKeyboardButton("📋 View All Notes", callback_data='view_notes')],
                [InlineKeyboardButton("➕ Another Note", callback_data='new_note')],
                [InlineKeyboardButton("📄 View This Note", callback_data=f'view_note_{note_id}')]
            ]
            await update.message.reply_text(
                f"✅ *Note saved!*\n📌 Title: {escape_markdown(title, version=2)}\n📄 Content: {escape_markdown(content[:100], version=2)}{'...' if len(content)>100 else ''}\n🆔 Note ID: #{note_id}",
                parse_mode=ParseMode.MARKDOWN_V2,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            context.user_data['awaiting_note'] = False

        elif context.user_data.get('awaiting_search'):
            query = text
            results = search_user_notes(user_id, query)
            if not results:
                await update.message.reply_text("🔍 No notes found.")
                return
            message = f"🔍 *Search Results for '{escape_markdown(query, version=2)}':*\n\n"
            keyboard = []
            for note in results[:10]:
                message += f"📌 #{note['note_id']}: {escape_markdown(note['title'], version=2)}\nCategory: {escape_markdown(note['category'], version=2)}\n\n"
                keyboard.append([InlineKeyboardButton(f"📄 #{note['note_id']}", callback_data=f'view_note_{note['note_id']}')])
            keyboard.append([InlineKeyboardButton("📋 Back to Notes", callback_data='view_notes')])
            await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=InlineKeyboardMarkup(keyboard))
            context.user_data['awaiting_search'] = False
    except Exception as e:
        logger.error(f"handle_message error: {e}")
        await update.message.reply_text("❌ Something went wrong!")

# ----------------- Add other handlers like my_notes, search_command, categories_command, button_handler -----------------
# (You can reuse your previous code but replace ParseMode.MARKDOWN -> ParseMode.MARKDOWN_V2 and escape dynamic text using escape_markdown)

# ----------------- Main -----------------
def main():
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("new", new_note))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    # Add your other handlers here...
    application.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 Notepad++ Bot running on Render...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
