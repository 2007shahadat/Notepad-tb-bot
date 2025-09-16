import os
import logging
import json
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from telegram.constants import ParseMode
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__) # Corrected 'name' to '__name__' for standard practice

# Get bot token from environment variable
BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    # If BOT_TOKEN is not set, raise an error to prevent the bot from starting
    raise ValueError("Please set BOT_TOKEN environment variable in your .env file or environment.")

# --- Global Data Storage and Persistence ---
user_data = {
    'notes': {},    # Stores notes: {user_id_str: [{note_obj}, ...]}
    'settings': {}  # Stores user-specific settings: {user_id_str: {'next_note_id': int}}
}

DATA_FILE = 'user_data.json' # The file used for storing all bot data

def save_user_data():
    """Save all user data (notes and settings) to the DATA_FILE."""
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(user_data, f, ensure_ascii=False, indent=4)
        logger.info("User data saved successfully.")
    except Exception as e:
        logger.error(f"Error saving user data: {e}")

def load_user_data():
    """Load all user data (notes and settings) from the DATA_FILE."""
    global user_data # Declare intent to modify the global user_data variable
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                user_data = json.load(f)
            logger.info("User data loaded successfully.")
        else:
            logger.info(f"User data file '{DATA_FILE}' not found, starting with empty data.")
            user_data = {'notes': {}, 'settings': {}} # Initialize if file doesn't exist
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding JSON from user data file: {e}. Starting with empty data.")
        user_data = {'notes': {}, 'settings': {}} # Fallback to empty data on corruption
    except Exception as e:
        logger.error(f"Error loading user data: {e}. Starting with empty data.")
        user_data = {'notes': {}, 'settings': {}} # Fallback on other errors

# Load existing data when the bot starts
load_user_data()

# --- Helper functions for note management ---

NOTES_PER_PAGE = 5 # Define how many notes to show per page for pagination

def get_user_notes(user_id):
    """Get all notes for a specific user, sorted by creation date (newest first)."""
    return sorted(
        user_data['notes'].get(str(user_id), []),
        key=lambda x: datetime.fromisoformat(x['created_at']),
        reverse=True
    )

def add_user_note(user_id, title, content, category='General'):
    """Add a new note for a user with a unique incrementing ID."""
    user_id_str = str(user_id)

    if user_id_str not in user_data['notes']:
        user_data['notes'][user_id_str] = []
    if user_id_str not in user_data['settings']:
        user_data['settings'][user_id_str] = {'next_note_id': 1}

    user_settings = user_data['settings'][user_id_str]
    note_id = user_settings['next_note_id']
    user_settings['next_note_id'] += 1

    note = {
        'title': title,
        'content': content,
        'category': category,
        'created_at': datetime.now().isoformat(),
        'note_id': note_id
    }

    user_data['notes'][user_id_str].append(note)
    save_user_data()
    return note['note_id']

def delete_user_note(user_id, note_id):
    """Delete a specific note by its ID for a given user."""
    user_id_str = str(user_id)
    if user_id_str in user_data['notes']:
        initial_len = len(user_data['notes'][user_id_str])
        user_data['notes'][user_id_str] = [note for note in user_data['notes'][user_id_str] if note['note_id'] != note_id]
        if len(user_data['notes'][user_id_str]) < initial_len:
            save_user_data()
            return True
    return False

def get_user_note(user_id, note_id):
    """Retrieve a specific note by its ID for a given user."""
    user_id_str = str(user_id)
    if user_id_str in user_data['notes']:
        for note in user_data['notes'][user_id_str]:
            if note['note_id'] == note_id:
                return note
    return None

def update_user_note_category(user_id, note_id, new_category):
    """Update the category of an existing note."""
    user_id_str = str(user_id)
    if user_id_str in user_data['notes']:
        for note in user_data['notes'][user_id_str]:
            if note['note_id'] == note_id:
                note['category'] = new_category
                save_user_data()
                return True
    return False

def search_user_notes(user_id, query):
    """Search notes for a user by matching query in title, content, or category (case-insensitive)."""
    user_id_str = str(user_id)
    if user_id_str not in user_data['notes']:
        return []

    query = query.lower()
    results = []
    for note in user_data['notes'][user_id_str]:
        if (query in note['title'].lower() or
            query in note['content'].lower() or
            query in note['category'].lower()):
            results.append(note)

    return sorted(results, key=lambda x: datetime.fromisoformat(x['created_at']), reverse=True)

def get_user_categories(user_id):
    """Get all unique categories associated with a user's notes, sorted alphabetically."""
    user_id_str = str(user_id)
    if user_id_str not in user_data['notes']:
        return []

    categories = set()
    for note in user_data['notes'][user_id_str]:
        categories.add(note['category'])

    return sorted(list(categories))

# --- Bot handlers ---

# Define a constant for the 'Back to Main Menu' button for reusability
BACK_TO_MAIN_MENU_BUTTON = InlineKeyboardButton("🔙 Main Menu", callback_data='back_to_main')

def get_main_keyboard():
    """Returns the main inline keyboard markup for bot navigation."""
    keyboard = [
        [InlineKeyboardButton("➕ New Note", callback_data='new_note')],
        [InlineKeyboardButton("📋 My Notes", callback_data='view_notes_page_0')],
        [InlineKeyboardButton("🔍 Search Notes", callback_data='search_notes')],
        [InlineKeyboardButton("🗂️ Categories", callback_data='view_categories')],
        [InlineKeyboardButton("📊 Statistics", callback_data='stats')],
        [InlineKeyboardButton("❓ Help Guide", callback_data='help')]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /start command, sending a welcome message and the main menu."""
    user = update.effective_user
    welcome_text = f"""
👋 Hello {user.first_name}! Welcome to *Notepad++ Bot*! 📝

✨ *Features:*
• 📝 Create and save notes with titles
• 📋 View and organize notes by categories (with *pagination*!)
• 🔍 Search through your notes
• 🗂️ Categorize your notes (and *edit them*!)
• ⚡ Quick inline navigation
• 🗑️ Delete notes
• 📈 User Statistics
• 🚀 Markdown support for formatted text

*Quick Commands:*
`/new` - Create a new note
`/mynotes` - View your notes
`/search` - Search notes
`/categories` - Manage categories
`/help` - Show help guide
`/stats` - Show statistics
`/clear` - Clear all notes

Simply send me any text to save it as a quick note! 🚀
"""
    await update.message.reply_text(welcome_text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())

async def new_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Initiates the process for creating a new note."""
    context.user_data['awaiting_note'] = True
    context.user_data.pop('awaiting_search', None)
    context.user_data.pop('awaiting_category_for_note_id', None)

    target_object = update.message if update.message else update.callback_query
    reply_func = target_object.reply_text if update.message else target_object.edit_message_text

    await reply_func(
        "📝 *Let's create a new note!*\n\n"
        "Please send me the text for your note. You can also include a title and category by formatting it like:\n"
        "`Title: Your Title Here\nCategory: Your Category Name\nContent: Your content here`\n\n"
        "Or just send the content, and I'll auto-generate a title and assign it to the 'General' category!",
        parse_mode=ParseMode.MARKDOWN
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles incoming text messages based on the current user state (e.g., new note, search query, category update)."""
    user_id = update.effective_user.id
    text = update.message.text

    if 'awaiting_category_for_note_id' in context.user_data:
        note_id = context.user_data.pop('awaiting_category_for_note_id')
        new_category = text.strip()

        note = get_user_note(user_id, note_id)
        if note and update_user_note_category(user_id, note_id, new_category):
            keyboard = [
                [InlineKeyboardButton("📄 View Note", callback_data=f'view_note_{note_id}')],
                [InlineKeyboardButton("📋 My Notes", callback_data='view_notes_page_0')],
                [InlineKeyboardButton("➕ New Note", callback_data='new_note')],
                [BACK_TO_MAIN_MENU_BUTTON] # Added Back button
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                f"✅ *Category for Note #{note_id} updated to '{new_category}' successfully!*",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text("❌ Failed to update category. Note might not exist or an error occurred.")
        return

    if context.user_data.get('awaiting_note'):
        context.user_data['awaiting_note'] = False

        title = None
        category = 'General'
        content = text

        lines = text.split('\n')
        parsed_content_lines = []
        is_content_explicitly_set = False

        for line in lines:
            line_lower = line.lower()
            if line_lower.startswith('title:'):
                title = line.split(':', 1)[1].strip()
            elif line_lower.startswith('category:'):
                category = line.split(':', 1)[1].strip()
            elif line_lower.startswith('content:'):
                content = line.split(':', 1)[1].strip()
                is_content_explicitly_set = True
                parsed_content_lines = []
            else:
                if not is_content_explicitly_set and not (line_lower.startswith('title:') or line_lower.startswith('category:')):
                    parsed_content_lines.append(line)

        if not is_content_explicitly_set:
            content = "\n".join(parsed_content_lines).strip()
            if not content:
                content = text

        if not title:
            title = content[:50] + '...' if len(content) > 50 else content
            if not title:
                title = "Untitled Note"

        note_id = add_user_note(user_id, title, content, category)

        keyboard = [
            [InlineKeyboardButton("📋 View All Notes", callback_data='view_notes_page_0')],
            [InlineKeyboardButton("➕ Another Note", callback_data='new_note')],
            [InlineKeyboardButton("📄 View This Note", callback_data=f'view_note_{note_id}')],
            [BACK_TO_MAIN_MENU_BUTTON] # Added Back button
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"✅ *Note saved successfully!* (`#{note_id}`)\n\n"
            f"📌 *Title:* {title}\n"
            f"🗂️ *Category:* {category}\n"
            f"📄 *Content:* {content[:150]}{'...' if len(content) > 150 else ''}\n\n"
            f"You can view, edit category, or delete this note using buttons!",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
        return

    elif context.user_data.get('awaiting_search'):
        context.user_data['awaiting_search'] = False
        query = text
        results = search_user_notes(user_id, query)

        context.user_data['last_search_results'] = results
        context.user_data['last_search_query'] = query

        await send_search_results_page(update.message, context, query, 0)
        return

    else:
        title = text[:50] + '...' if len(text) > 50 else text
        if not title:
            title = "Untitled Quick Note"

        note_id = add_user_note(user_id, title, text, category='Quick Notes')

        keyboard = [
            [InlineKeyboardButton("📋 View All Notes", callback_data='view_notes_page_0')],
            [InlineKeyboardButton("➕ Another Note", callback_data='new_note')],
            [InlineKeyboardButton("📄 View This Note", callback_data=f'view_note_{note_id}')],
            [BACK_TO_MAIN_MENU_BUTTON] # Added Back button
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"✍️ *Quick Note saved!* (`#{note_id}`)\n\n"
            f"📌 *Title:* {title}\n"
            f"🗂️ *Category:* Quick Notes\n"
            f"📄 *Content:* {text[:100]}{'...' if len(text) > 100 else ''}\n\n"
            f"You can use the `/new` command or the '➕ New Note' button for more detailed options!",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )


async def send_notes_page(target_message, context, page: int, category: str = None):
    """Helper function to send a paginated list of notes (either via command or callback)."""
    user_id = target_message.chat.id
    all_notes = get_user_notes(user_id)

    if category and category != 'All':
        all_notes = [note for note in all_notes if note['category'] == category]
        
    if not all_notes:
        text = f"📭 You don't have any notes yet {'in the category *'+category+'*' if category else ''}. Use /new to create one!"
        reply_func = target_message.reply_text if target_message.from_user else target_message.edit_message_text
        # Ensure the main keyboard is always available if no notes are found
        await reply_func(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())
        return

    total_pages = (len(all_notes) + NOTES_PER_PAGE - 1) // NOTES_PER_PAGE
    current_page = max(0, min(page, total_pages - 1))
    start_index = current_page * NOTES_PER_PAGE
    end_index = start_index + NOTES_PER_PAGE
    notes_on_page = all_notes[start_index:end_index]

    message_lines = [f"📋 *Your Notes ({'Category: *' + category + '*' if category else 'All Notes'} - Page {current_page + 1}/{total_pages}):*\n"]
    keyboard = []

    for note in notes_on_page:
        message_lines.append(f"• #{note['note_id']}: *{note['title']}* ({note['category']})")
        keyboard.append([
            InlineKeyboardButton(f"📄 View #{note['note_id']}", callback_data=f'view_note_{note["note_id"]}'),
            InlineKeyboardButton(f"❌ Delete #{note['note_id']}", callback_data=f'delete_note_{note["note_id"]}')
        ])

    pagination_buttons = []
    if current_page > 0:
        pagination_buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data=f'view_notes_page_{current_page-1}{f"_cat_{category}" if category else ""}'))
    if current_page < total_pages - 1:
        pagination_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f'view_notes_page_{current_page+1}{f"_cat_{category}" if category else ""}'))
    if pagination_buttons:
        keyboard.append(pagination_buttons)

    keyboard.extend([
        [InlineKeyboardButton("🔍 Search Notes", callback_data='search_notes')],
        [InlineKeyboardButton("🗂️ View Categories", callback_data='view_categories')],
        [InlineKeyboardButton("➕ New Note", callback_data='new_note')],
        [BACK_TO_MAIN_MENU_BUTTON] # Added Back button
    ])

    reply_markup = InlineKeyboardMarkup(keyboard)
    text_to_send = "\n".join(message_lines)

    if target_message.from_user:
        await target_message.reply_text(text_to_send, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
    else:
        await target_message.edit_message_text(text_to_send, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)

async def my_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /mynotes command to show the first page of user's notes."""
    await send_notes_page(update.message, context, 0)

async def send_search_results_page(target_message, context, query: str, page: int):
    """Helper function to send a paginated list of search results."""
    user_id = target_message.chat.id
    results = context.user_data.get('last_search_results', [])
    
    if not results:
        text = "🔍 No notes found matching your search."
        reply_func = target_message.reply_text if target_message.from_user else target_message.edit_message_text
        await reply_func(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())
        return

    total_pages = (len(results) + NOTES_PER_PAGE - 1) // NOTES_PER_PAGE
    current_page = max(0, min(page, total_pages - 1))
    start_index = current_page * NOTES_PER_PAGE
    end_index = start_index + NOTES_PER_PAGE
    notes_on_page = results[start_index:end_index]

    message_lines = [f"🔍 *Search Results for '{query}' (Page {current_page + 1}/{total_pages}):*\n"]
    keyboard = []

    for note in notes_on_page:
        message_lines.append(f"• #{note['note_id']}: *{note['title']}* ({note['category']})")
        keyboard.append([
            InlineKeyboardButton(f"📄 View #{note['note_id']}", callback_data=f'view_note_{note["note_id"]}'),
            InlineKeyboardButton(f"❌ Delete #{note['note_id']}", callback_data=f'delete_note_{note["note_id"]}')
        ])

    pagination_buttons = []
    if current_page > 0:
        pagination_buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data=f'search_results_page_{current_page-1}'))
    if current_page < total_pages - 1:
        pagination_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f'search_results_page_{current_page+1}'))
    if pagination_buttons:
        keyboard.append(pagination_buttons)

    keyboard.extend([
        [InlineKeyboardButton("📋 Back to Notes", callback_data='view_notes_page_0')], # This goes back to all notes, not main menu
        [InlineKeyboardButton("➕ New Note", callback_data='new_note')],
        [BACK_TO_MAIN_MENU_BUTTON] # Added Back button
    ])
    reply_markup = InlineKeyboardMarkup(keyboard)

    text_to_send = "\n".join(message_lines)
    reply_func = target_message.reply_text if target_message.from_user else target_message.edit_message_text
    await reply_func(text_to_send, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)


async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /search command, prompting the user for a search query."""
    context.user_data['awaiting_search'] = True
    context.user_data.pop('awaiting_note', None)
    context.user_data.pop('awaiting_category_for_note_id', None)

    await update.message.reply_text("🔍 What would you like to search for in your notes? (Enter keywords, title, content, or category)")

async def categories_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /categories command, showing all unique categories and options to view notes within them."""
    user_id = update.effective_user.id
    categories = get_user_categories(user_id)

    target_object = update.message if update.message else update.callback_query
    reply_func = target_object.reply_text if update.message else target_object.edit_message_text

    if not categories:
        text = "🗂️ You don't have any categories yet. Notes will be saved under 'General' or 'Quick Notes' by default."
        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ New Note", callback_data='new_note')],
            [BACK_TO_MAIN_MENU_BUTTON] # Added Back button
        ])
        await reply_func(text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
        return

    message = "🗂️ *Your Categories:*\n\n"
    keyboard = []
    for category in categories:
        notes_in_category = [note for note in get_user_notes(user_id) if note['category'] == category]
        message += f"• *{category}* ({len(notes_in_category)} notes)\n"
        keyboard.append([InlineKeyboardButton(f"View '{category}' Notes", callback_data=f'view_notes_page_0_cat_{category}')])

    keyboard.append([InlineKeyboardButton("📋 View All Notes", callback_data='view_notes_page_0')])
    keyboard.append([InlineKeyboardButton("➕ New Note", callback_data='new_note')])
    keyboard.append([BACK_TO_MAIN_MENU_BUTTON]) # Added Back button
    reply_markup = InlineKeyboardMarkup(keyboard)

    await reply_func(message, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles all inline button presses and routes them to appropriate logic."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data

    context.user_data.pop('awaiting_note', None)
    context.user_data.pop('awaiting_search', None)
    context.user_data.pop('awaiting_category_for_note_id', None)

    if data == 'new_note':
        await new_note(update, context)

    elif data.startswith('view_notes_page_'):
        parts = data.split('_')
        try:
            page = int(parts[3])
            category = None
            if len(parts) > 4 and parts[4] == 'cat':
                category = parts[5]
            
            await send_notes_page(query.message, context, page, category)
        except (ValueError, IndexError):
            await query.edit_message_text("❌ Invalid page or category information.", reply_markup=get_main_keyboard())

    elif data == 'search_notes':
        context.user_data['awaiting_search'] = True
        await query.edit_message_text("🔍 What would you like to search for in your notes?")
    
    elif data.startswith('search_results_page_'):
        try:
            page = int(data.split('_')[-1])
            query_text = context.user_data.get('last_search_query', '')
            if not query_text:
                await query.edit_message_text("❌ No active search query found. Please search again.", reply_markup=get_main_keyboard())
                return
            await send_search_results_page(query.message, context, query_text, page)
        except (ValueError, IndexError):
            await query.edit_message_text("❌ Invalid page information for search results.", reply_markup=get_main_keyboard())

    elif data == 'view_categories':
        await categories_command(update, context)

    elif data.startswith('view_note_'):
        try:
            note_id = int(data.split('_')[-1])
        except ValueError:
            await query.edit_message_text("❌ Invalid note ID format.", reply_markup=get_main_keyboard())
            return

        note = get_user_note(user_id, note_id)

        if note:
            created_date = datetime.fromisoformat(note['created_at']).strftime('%Y-%m-%d %H:%M')
            
            keyboard = [
                [InlineKeyboardButton("📋 Back to Notes", callback_data='view_notes_page_0')],
                [InlineKeyboardButton("✏️ Edit Category", callback_data=f'edit_category_{note_id}')],
                [InlineKeyboardButton("❌ Delete This Note", callback_data=f'delete_note_{note_id}')],
                [InlineKeyboardButton("➕ New Note", callback_data='new_note')],
                [BACK_TO_MAIN_MENU_BUTTON] # Added Back button
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
        else:
            await query.edit_message_text("❌ Note not found or already deleted.", reply_markup=get_main_keyboard())

    elif data.startswith('edit_category_'):
        try:
            note_id = int(data.split('_')[-1])
        except ValueError:
            await query.edit_message_text("❌ Invalid note ID format.", reply_markup=get_main_keyboard())
            return
        
        note = get_user_note(user_id, note_id)
        if note:
            context.user_data['awaiting_category_for_note_id'] = note_id
            await query.edit_message_text(
                f"✏️ *Editing category for Note #{note_id}* (`{note['title'][:30]}...`)\n\n"
                "Please send me the *new category name* for this note.\n"
                f"Current category: `{note['category']}`",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await query.edit_message_text("❌ Note not found or already deleted.", reply_markup=get_main_keyboard())

    elif data.startswith('delete_note_'):
        try:
            note_id = int(data.split('_')[-1])
        except ValueError:
            await query.edit_message_text("❌ Invalid note ID format.", reply_markup=get_main_keyboard())
            return

        success = delete_user_note(user_id, note_id)

        if success:
            keyboard = [
                [InlineKeyboardButton("📋 View Notes", callback_data='view_notes_page_0')],
                [InlineKeyboardButton("➕ New Note", callback_data='new_note')],
                [BACK_TO_MAIN_MENU_BUTTON] # Added Back button
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"✅ *Note #{note_id} deleted successfully!*",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
        else:
            await query.edit_message_text("❌ Note not found or already deleted.", reply_markup=get_main_keyboard())

    elif data == 'stats':
        notes = get_user_notes(user_id)
        categories = get_user_categories(user_id)

        total_notes = len(notes)
        total_categories = len(categories)

        stats_text = f"""
📊 *Your Statistics*

📝 *Total Notes:* {total_notes}
🗂️ *Categories:* {total_categories}
📅 *Last Updated:* {datetime.now().strftime('%Y-%m-%d %H:%M')}

Keep adding notes to build your knowledge base! 🚀
"""
        keyboard = [[BACK_TO_MAIN_MENU_BUTTON]] # Uses the constant
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(stats_text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)

    elif data == 'help':
        help_text = """
🤖 *Notepad++ Bot Help Guide*

*Commands:*
`/start` - Start the bot and see the main menu
`/new` - Create a new note
`/mynotes` - View your notes (with pagination)
`/search` - Search through notes
`/categories` - View and navigate through categories
`/stats` - Show your note statistics
`/clear` - Clear all your notes
`/help` - Show this help guide

*How to Create Notes:*
1.  Simply send any text message to save it as a "Quick Note".
2.  For detailed notes, use the format:
    `Title: My Awesome Note`
    `Category: Ideas`
    `Content: This is the detailed content of my note, it can be long and support Markdown! *bold*, _italic_, `code` etc.`
    (Category and Title are optional, will be auto-generated or default to 'General'/'Quick Notes'.)

*Navigation:*
• Use the inline buttons provided with messages for easy navigation between features.
• You can *edit a note's category* by viewing the note and clicking 'Edit Category'.
• The "🔙 Main Menu" button will take you back to the bot's main options.

📝 Happy note-taking!
"""
        keyboard = [[BACK_TO_MAIN_MENU_BUTTON]] # Uses the constant
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(help_text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)

    elif data == 'back_to_main':
        user = query.from_user
        welcome_text = f"👋 *Welcome back {user.first_name}!* What would you like to do?"
        await query.edit_message_text(welcome_text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /help command."""
    help_text = """
🤖 *Notepad++ Bot Help*

*Quick Commands:*
`/start` - Start the bot
`/new` - Create new note
`/mynotes` - View your notes
`/search` - Search notes
`/categories` - View categories
`/stats` - Show statistics
`/clear` - Clear all notes
`/help` - Show help

Simply send any text message to save it as a note! Use the inline buttons for easy navigation, including the '🔙 Main Menu' button.
"""
    keyboard = [[BACK_TO_MAIN_MENU_BUTTON]] # Added for command handler too
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /stats command, showing user's note statistics."""
    user_id = update.effective_user.id
    notes = get_user_notes(user_id)
    categories = get_user_categories(user_id)

    total_notes = len(notes)
    total_categories = len(categories)

    stats_text = f"""
📊 *Your Statistics*

📝 *Total Notes:* {total_notes}
🗂️ *Categories:* {total_categories}
📅 *Last Updated:* {datetime.now().strftime('%Y-%m-%d %H:%M')}

Keep adding notes to build your knowledge base! 🚀
"""
    keyboard = [[BACK_TO_MAIN_MENU_BUTTON]] # Added for command handler too
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(stats_text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)

async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /clear command, deleting all notes for the current user."""
    user_id = update.effective_user.id
    user_id_str = str(user_id)

    if user_id_str in user_data['notes'] and user_data['notes'][user_id_str]:
        user_data['notes'][user_id_str] = []
        if user_id_str in user_data['settings']:
            user_data['settings'][user_id_str]['next_note_id'] = 1
        save_user_data()
        keyboard = [[BACK_TO_MAIN_MENU_BUTTON]] # Added Back button
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("✅ All your notes have been cleared!", reply_markup=reply_markup)
    else:
        keyboard = [[BACK_TO_MAIN_MENU_BUTTON]] # Added Back button
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("📭 You don't have any notes to clear.", reply_markup=reply_markup)

def main():
    """Starts the bot by initializing the Telegram Application and adding all handlers."""
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("new", new_note))
    application.add_handler(CommandHandler("mynotes", my_notes))
    application.add_handler(CommandHandler("search", search_command))
    application.add_handler(CommandHandler("categories", categories_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("clear", clear_command))
    
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    application.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 Notepad++ Bot is running...")
    print(f"💾 Using JSON file storage: {DATA_FILE}")
    print("🚀 Ready to receive messages!")

    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
