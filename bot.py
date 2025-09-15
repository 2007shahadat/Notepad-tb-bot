import os
import logging
import json
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from telegram.constants import ParseMode

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Get bot token from environment variable
BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    raise ValueError("Please set BOT_TOKEN environment variable")

# Dictionary to store user data (in memory, for demo purposes)
# In production, you might want to use a simple file-based storage
user_notes = {}
user_settings = {}

def save_user_data():
    """Save user data to a file (optional)"""
    data = {
        'notes': user_notes,
        'settings': user_settings
    }
    with open('user_data.json', 'w') as f:
        json.dump(data, f)

def load_user_data():
    """Load user data from file (optional)"""
    global user_notes, user_settings
    try:
        with open('user_data.json', 'r') as f:
            data = json.load(f)
            user_notes = data.get('notes', {})
            user_settings = data.get('settings', {})
    except FileNotFoundError:
        user_notes = {}
        user_settings = {}

# Load existing data if available
load_user_data()

def get_user_notes(user_id):
    """Get all notes for a user"""
    return user_notes.get(str(user_id), [])

def add_user_note(user_id, message_id, title, content, category='General'):
    """Add a new note for user"""
    user_id_str = str(user_id)
    if user_id_str not in user_notes:
        user_notes[user_id_str] = []
    
    note = {
        'message_id': message_id,
        'title': title,
        'content': content,
        'category': category,
        'created_at': datetime.now().isoformat(),
        'note_id': len(user_notes[user_id_str]) + 1
    }
    
    user_notes[user_id_str].append(note)
    save_user_data()
    return note['note_id']

def delete_user_note(user_id, note_id):
    """Delete a user note"""
    user_id_str = str(user_id)
    if user_id_str in user_notes:
        user_notes[user_id_str] = [note for note in user_notes[user_id_str] if note['note_id'] != note_id]
        save_user_data()
        return True
    return False

def get_user_note(user_id, note_id):
    """Get a specific note"""
    user_id_str = str(user_id)
    if user_id_str in user_notes:
        for note in user_notes[user_id_str]:
            if note['note_id'] == note_id:
                return note
    return None

def search_user_notes(user_id, query):
    """Search notes for a user"""
    user_id_str = str(user_id)
    if user_id_str not in user_notes:
        return []
    
    query = query.lower()
    results = []
    for note in user_notes[user_id_str]:
        if (query in note['title'].lower() or 
            query in note['content'].lower() or 
            query in note['category'].lower()):
            results.append(note)
    
    return results

def get_user_categories(user_id):
    """Get all categories for a user"""
    user_id_str = str(user_id)
    if user_id_str not in user_notes:
        return []
    
    categories = set()
    for note in user_notes[user_id_str]:
        categories.add(note['category'])
    
    return sorted(list(categories))

# Bot handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    user = update.effective_user
    welcome_text = f"""
👋 *Hello {user.first_name}!* Welcome to Notepad++ Bot! 📝

✨ *Features:*
• 📝 Create and save notes with titles
• 📋 View and organize notes by categories
• 🔍 Search through your notes
• 🗂️ Categorize your notes
• ⚡ Quick inline navigation
• 🗑️ Delete notes

*Quick Commands:*
/new - Create a new note
/mynotes - View your notes
/search - Search notes
/categories - Manage categories
/help - Show help guide

Simply send me any text to save it as a note! 🚀
"""
    
    keyboard = [
        [InlineKeyboardButton("➕ New Note", callback_data='new_note')],
        [InlineKeyboardButton("📋 My Notes", callback_data='view_notes')],
        [InlineKeyboardButton("🔍 Search Notes", callback_data='search_notes')],
        [InlineKeyboardButton("🗂️ Categories", callback_data='view_categories')],
        [InlineKeyboardButton("❓ Help Guide", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(welcome_text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)

async def new_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start creating a new note."""
    context.user_data['awaiting_note'] = True
    await update.message.reply_text(
        "📝 *Let's create a new note!*\n\n"
        "Please send me the text for your note. You can also include a title by formatting it like:\n"
        "*Title:* Your Title Here\n*Content:* Your content here\n\n"
        "Or just send the content and I'll auto-generate a title!",
        parse_mode=ParseMode.MARKDOWN
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages and save as notes."""
    if context.user_data.get('awaiting_note'):
        user_id = update.effective_user.id
        text = update.message.text
        
        # Parse title and content
        title = None
        content = text
        
        if text.startswith('Title:') or text.startswith('title:'):
            lines = text.split('\n')
            for line in lines:
                if line.lower().startswith('title:'):
                    title = line.split(':', 1)[1].strip()
                elif line.lower().startswith('content:'):
                    content = line.split(':', 1)[1].strip()
        
        if not title:
            # Auto-generate title from first few words
            title = content[:30] + '...' if len(content) > 30 else content
        
        # Save the message and get its ID
        sent_message = await update.message.reply_text("💾 Saving your note...")
        message_id = sent_message.message_id
        
        # Save to user data
        note_id = add_user_note(user_id, message_id, title, content)
        
        keyboard = [
            [InlineKeyboardButton("📋 View All Notes", callback_data='view_notes')],
            [InlineKeyboardButton("➕ Another Note", callback_data='new_note')],
            [InlineKeyboardButton("📄 View This Note", callback_data=f'view_note_{note_id}')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Edit the original message to show success
        await sent_message.edit_text(
            f"✅ *Note saved successfully!*\n\n"
            f"📌 *Title:* {title}\n"
            f"📄 *Content:* {content[:100]}{'...' if len(content) > 100 else ''}\n\n"
            f"🆔 Note ID: #{note_id}",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
        context.user_data['awaiting_note'] = False
    
    elif context.user_data.get('awaiting_search'):
        user_id = update.effective_user.id
        query = update.message.text
        results = search_user_notes(user_id, query)
        
        if not results:
            await update.message.reply_text("🔍 No notes found matching your search.")
            return
        
        message = f"🔍 *Search Results for '{query}':*\n\n"
        keyboard = []
        
        for note in results[:10]:  # Limit to 10 results
            message += f"📌 #{note['note_id']}: {note['title']}\nCategory: {note['category']}\n\n"
            keyboard.append([InlineKeyboardButton(f"📄 #{note['note_id']}: {note['title'][:20]}...", callback_data=f'view_note_{note["note_id"]}')])
        
        keyboard.append([InlineKeyboardButton("📋 Back to Notes", callback_data='view_notes')])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
        context.user_data['awaiting_search'] = False

async def my_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's notes."""
    user_id = update.effective_user.id
    notes = get_user_notes(user_id)
    
    if not notes:
        await update.message.reply_text("📭 You don't have any notes yet. Use /new to create one!")
        return
    
    message = "📋 *Your Notes:*\n\n"
    keyboard = []
    
    for note in notes[:10]:  # Show last 10 notes
        message += f"#{note['note_id']}: {note['title']} ({note['category']})\n"
        keyboard.append([
            InlineKeyboardButton(f"📄 #{note['note_id']}", callback_data=f'view_note_{note["note_id"]}'),
            InlineKeyboardButton(f"❌ #{note['note_id']}", callback_data=f'delete_note_{note["note_id"]}')
        ])
    
    keyboard.extend([
        [InlineKeyboardButton("🔍 Search Notes", callback_data='search_notes')],
        [InlineKeyboardButton("🗂️ View Categories", callback_data='view_categories')],
        [InlineKeyboardButton("➕ New Note", callback_data='new_note')]
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Initiate search."""
    context.user_data['awaiting_search'] = True
    await update.message.reply_text("🔍 What would you like to search for in your notes?")

async def categories_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show categories."""
    user_id = update.effective_user.id
    categories = get_user_categories(user_id)
    
    if not categories:
        await update.message.reply_text("You don't have any categories yet. Notes will be saved under 'General' by default.")
        return
    
    message = "🗂️ *Your Categories:*\n\n"
    for category in categories:
        notes = [note for note in get_user_notes(user_id) if note['category'] == category]
        message += f"• {category} ({len(notes)} notes)\n"
    
    keyboard = [[InlineKeyboardButton("📋 View Notes", callback_data='view_notes')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline button presses."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    if data == 'new_note':
        context.user_data['awaiting_note'] = True
        await query.edit_message_text(
            "📝 *Let's create a new note!*\n\nPlease send me the text for your note...",
            parse_mode=ParseMode.MARKDOWN
        )
    
    elif data == 'view_notes':
        notes = get_user_notes(user_id)
        
        if not notes:
            await query.edit_message_text("📭 You don't have any notes yet.")
            return
        
        message = "📋 *Your Notes:*\n\n"
        keyboard = []
        
        for note in notes[:10]:
            message += f"#{note['note_id']}: {note['title']} ({note['category']})\n"
            keyboard.append([
                InlineKeyboardButton(f"📄 #{note['note_id']}", callback_data=f'view_note_{note["note_id"]}'),
                InlineKeyboardButton(f"❌ #{note['note_id']}", callback_data=f'delete_note_{note["note_id"]}')
            ])
        
        keyboard.extend([
            [InlineKeyboardButton("🔍 Search Notes", callback_data='search_notes')],
            [InlineKeyboardButton("🗂️ View Categories", callback_data='view_categories')],
            [InlineKeyboardButton("➕ New Note", callback_data='new_note')]
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(message, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
    
    elif data == 'search_notes':
        context.user_data['awaiting_search'] = True
        await query.edit_message_text("🔍 What would you like to search for in your notes?")
    
    elif data == 'view_categories':
        categories = get_user_categories(user_id)
        
        if not categories:
            await query.edit_message_text("You don't have any categories yet.")
            return
        
        message = "🗂️ *Your Categories:*\n\n"
        for category in categories:
            notes = [note for note in get_user_notes(user_id) if note['category'] == category]
            message += f"• {category} ({len(notes)} notes)\n"
        
        keyboard = [
            [InlineKeyboardButton("📋 View Notes", callback_data='view_notes')],
            [InlineKeyboardButton("➕ New Note", callback_data='new_note')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(message, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
    
    elif data.startswith('view_note_'):
        note_id = int(data.split('_')[-1])
        note = get_user_note(user_id, note_id)
        
        if note:
            created_date = datetime.fromisoformat(note['created_at']).strftime('%Y-%m-%d %H:%M')
            
            keyboard = [
                [InlineKeyboardButton("📋 Back to Notes", callback_data='view_notes')],
                [InlineKeyboardButton("❌ Delete This Note", callback_data=f'delete_note_{note_id}')],
                [InlineKeyboardButton("➕ New Note", callback_data='new_note')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"📄 *Note #{note_id}*\n\n"
                f"📌 *Title:* {note['title']}\n"
                f"🗂️ *Category:* {note['category']}\n"
                f"🕒 *Created:* {created_date}\n\n"
                f"*Content:*\n{note['content']}",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
    
    elif data.startswith('delete_note_'):
        note_id = int(data.split('_')[-1])
        success = delete_user_note(user_id, note_id)
        
        if success:
            keyboard = [
                [InlineKeyboardButton("📋 View Notes", callback_data='view_notes')],
                [InlineKeyboardButton("➕ New Note", callback_data='new_note')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"✅ *Note #{note_id} deleted successfully!*",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
        else:
            await query.edit_message_text("❌ Note not found or already deleted.")
    
    elif data == 'help':
        help_text = """
🤖 *Notepad++ Bot Help Guide*

*Commands:*
/start - Start the bot
/new - Create a new note
/mynotes - View your notes
/search - Search through notes
/categories - View categories
/help - Show this help

*How to use:*
1. Send any text to save as note
2. Use format: *Title:* Your Title\\n*Content:* Your content
3. Or just send content for auto-title
4. Use buttons to navigate easily

*Features:*
• 📝 Note taking with titles
• 🗂️ Category organization
• 🔍 Full-text search
• ⚡ Quick inline buttons
• 💾 Telegram message storage

📝 *Happy note-taking!*
"""
        keyboard = [[InlineKeyboardButton("🔙 Main Menu", callback_data='back_to_main')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(help_text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
    
    elif data == 'back_to_main':
        user = query.from_user
        welcome_text = f"👋 *Welcome back {user.first_name}!* What would you like to do?"
        
        keyboard = [
            [InlineKeyboardButton("➕ New Note", callback_data='new_note')],
            [InlineKeyboardButton("📋 My Notes", callback_data='view_notes')],
            [InlineKeyboardButton("🔍 Search Notes", callback_data='search_notes')],
            [InlineKeyboardButton("🗂️ Categories", callback_data='view_categories')],
            [InlineKeyboardButton("❓ Help Guide", callback_data='help')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(welcome_text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a help message."""
    help_text = """
🤖 *Notepad++ Bot Help*

*Quick Commands:*
/start - Start the bot
/new - Create new note
/mynotes - View your notes
/search - Search notes
/categories - View categories
/help - Show help

Simply send any text message to save it as a note! Use the inline buttons for easy navigation.
"""
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user statistics."""
    user_id = update.effective_user.id
    notes = get_user_notes(user_id)
    categories = get_user_categories(user_id)
    
    total_notes = len(notes)
    total_categories = len(categories)
    
    stats_text = f"""
📊 *Your Statistics*

📝 Total Notes: {total_notes}
🗂️ Categories: {total_categories}
📅 Account Created: {datetime.now().strftime('%Y-%m-%d')}

Keep adding notes to build your knowledge base! 🚀
"""
    await update.message.reply_text(stats_text, parse_mode=ParseMode.MARKDOWN)

async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clear all notes."""
    user_id = update.effective_user.id
    user_id_str = str(user_id)
    
    if user_id_str in user_notes:
        del user_notes[user_id_str]
        save_user_data()
        await update.message.reply_text("✅ All your notes have been cleared!")
    else:
        await update.message.reply_text("📭 You don't have any notes to clear.")

def main():
    """Start the bot."""
    # Create the Application
    application = Application.builder().token(BOT_TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("new", new_note))
    application.add_handler(CommandHandler("mynotes", my_notes))
    application.add_handler(CommandHandler("search", search_command))
    application.add_handler(CommandHandler("categories", categories_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("clear", clear_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Start the Bot
    print("🤖 Notepad++ Bot is running...")
    print("💾 Using Telegram message storage")
    print("🚀 Ready to receive messages!")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
