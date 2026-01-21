"""Telegram interactive functions for human-in-the-loop."""
import os
import uuid
import asyncio
import threading
import time
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from telegram.error import TelegramError
from utils import truncate_post_to_limit

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

# Global state for pending interactions
_pending_responses = {}
_application = None
_bot_running = False


def _start_bot():
    """Start the Telegram bot in background."""
    global _application, _bot_running
    
    if not TELEGRAM_BOT_TOKEN or _bot_running:
        return
    
    async def main():
        global _application, _bot_running
        _application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        
        # Add handlers
        _application.add_handler(CallbackQueryHandler(_handle_callback))
        _application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _handle_message))
        
        await _application.initialize()
        await _application.start()
        await _application.updater.start_polling()
        _bot_running = True
        print("✅ Telegram bot started")
    
    def run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(main())
        loop.run_forever()
    
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    
    # Wait for bot to start
    import time
    for _ in range(10):
        if _bot_running:
            break
        time.sleep(0.5)


async def _handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks."""
    query = update.callback_query
    
    # Answer the callback query first (with error handling for old queries)
    try:
        await query.answer()
    except Exception as e:
        # Ignore errors about old queries - they're not critical
        print(f"⚠️ Callback query answer error (non-critical): {e}")
    
    if str(query.message.chat_id) != TELEGRAM_CHAT_ID:
        return
    
    callback_data = query.data
    
    # Helper function to edit message (handles both text and photo messages)
    async def edit_message_safe(text):
        try:
            # Try editing text first (for text messages)
            await query.edit_message_text(text, parse_mode='Markdown')
        except Exception:
            try:
                # If that fails, try editing caption (for photo messages)
                await query.edit_message_caption(caption=text, parse_mode='Markdown')
            except Exception as e:
                # If both fail, send a new message
                print(f"⚠️ Could not edit message, sending new one: {e}")
                await _send_message(text)
    
    # Parse and set result
    if callback_data.startswith("approve_post_"):
        context_id = callback_data.replace("approve_post_", "")
        await edit_message_safe("✅ *APPROVED!* Posting to Mastodon...")
        _set_response(context_id, "approve")
        
    elif callback_data.startswith("reject_post_"):
        context_id = callback_data.replace("reject_post_", "")
        await edit_message_safe("❌ *REJECTED!* Post not published.")
        _set_response(context_id, "reject")
        
    elif callback_data.startswith("edit_post_"):
        context_id = callback_data.replace("edit_post_", "")
        await edit_message_safe("✏️ *Edit Mode*")
        _set_response(context_id, "edit")
        
    elif callback_data.startswith("edit_text_"):
        context_id = callback_data.replace("edit_text_", "")
        if context_id in _pending_responses:
            current_text = _pending_responses[context_id].get('post_content', '')
            # Use the same context_id but mark as waiting for text
            _pending_responses[context_id]['waiting_for_text'] = True
            # Send text edit request - this will wait for user's reply
            await _send_text_edit_request(context_id, current_text)
            # Don't set response yet - wait for text reply in message handler
        else:
            _set_response(context_id, "edit_text")
        
    elif callback_data.startswith("edit_image_"):
        context_id = callback_data.replace("edit_image_", "")
        await edit_message_safe("🖼️ *Generating new image...*")
        _set_response(context_id, "edit_image")
        
    elif callback_data.startswith("edit_both_"):
        context_id = callback_data.replace("edit_both_", "")
        if context_id in _pending_responses:
            current_text = _pending_responses[context_id].get('post_content', '')
            # Create a separate context for text edit
            text_edit_context = f"{context_id}_text"
            _pending_responses[text_edit_context] = {
                'event': threading.Event(),
                'result': None,
                'waiting_for_text': True
            }
            await _send_text_edit_request(text_edit_context, current_text)
            await edit_message_safe("✏️ *Editing both text and image...*\n\nPlease edit the text first, then a new image will be generated.")
            # Set response to edit_both so main code knows what to do
            _set_response(context_id, "edit_both")
        else:
            _set_response(context_id, "edit_both")
        
    elif callback_data.startswith("approve_replies_all_"):
        context_id = callback_data.replace("approve_replies_all_", "")
        await edit_message_safe("✅ *APPROVED!* Posting all replies...")
        _set_response(context_id, "approve_all")
        
    elif callback_data.startswith("reject_replies_"):
        context_id = callback_data.replace("reject_replies_", "")
        await edit_message_safe("❌ *REJECTED!* No replies posted.")
        _set_response(context_id, "reject")
        
    elif callback_data.startswith("edit_replies_"):
        context_id = callback_data.replace("edit_replies_", "")
        await edit_message_safe("✏️ *Select replies to edit...*")
        _set_response(context_id, "edit_replies")
        
    elif callback_data == "mode_new_post":
        await edit_message_safe("📝 *Creating new post from Notion content...*")
        _set_response("mode_selection", "new_post")
        
    elif callback_data == "mode_craft_replies":
        await edit_message_safe("💬 *Crafting replies to existing posts...*")
        _set_response("mode_selection", "craft_replies")
        
    elif callback_data.startswith("edit_reply_"):
        parts = callback_data.replace("edit_reply_", "").split("_")
        reply_num = int(parts[0])
        context_id = "_".join(parts[1:])
        
        if context_id in _pending_responses:
            replies = _pending_responses[context_id].get('replies', [])
            if 1 <= reply_num <= len(replies):
                reply_text = replies[reply_num - 1].get('reply_text', '')
                await _send_single_reply_edit(reply_num, reply_text, f"{context_id}_{reply_num}")


async def _handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages for editing."""
    message = update.message
    if not message or not message.text:
        return
    
    if str(message.chat_id) != TELEGRAM_CHAT_ID:
        return
    
    text = message.text.strip()
    
    # Check if this is a reply to an edit request
    if message.reply_to_message:
        # Find context_id that's waiting for text
        for context_id, pending in list(_pending_responses.items()):
            if pending.get('waiting_for_text', False):
                # Validate and truncate
                if len(text) > 500:
                    text = truncate_post_to_limit(text, max_length=500)
                    await _send_message(f"⚠️ Text truncated to {len(text)} characters (500 limit)")
                
                # If this is edit_both, we still need to generate image after
                is_edit_both = pending.get('edit_both', False)
                
                # Set the response with the edited text
                _set_response(context_id, text)
                
                if is_edit_both:
                    await _send_message(f"✅ *Text updated!* ({len(text)} characters)\n\n🖼️ Now generating new image based on your updated text...")
                else:
                    await _send_message(f"✅ *Text updated!* ({len(text)} characters)")
                return


def _set_response(context_id, result):
    """Set response for a pending interaction."""
    if context_id in _pending_responses:
        _pending_responses[context_id]['result'] = result
        _pending_responses[context_id]['event'].set()  # This is a threading.Event, not asyncio.Event


def _send_message_sync(text, reply_markup=None, photo_path=None):
    """Send a message synchronously (creates new event loop)."""
    # Use asyncio.run() which creates a new event loop
    # This is safe because we're in the main thread, not the bot's thread
    asyncio.run(_send_message(text, reply_markup=reply_markup, photo_path=photo_path))


def _send_message_sync_async(coro):
    """Run an async coroutine synchronously."""
    asyncio.run(coro)


async def _send_message(text, reply_markup=None, photo_path=None):
    """Send a message via Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"⚠️  Telegram: {text}")
        return None
    
    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        chat_id = int(TELEGRAM_CHAT_ID)
        
        if photo_path and os.path.exists(photo_path):
            with open(photo_path, 'rb') as photo:
                return await bot.send_photo(
                    chat_id=chat_id,
                    photo=photo,
                    caption=text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
        else:
            return await bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
    except Exception as e:
        print(f"❌ Telegram error: {e}")
        return None


async def _send_text_edit_request(context_id, current_text):
    """Send text edit request."""
    text = f"📝 *Edit Text*\n\n"
    text += f"Current text:\n`{current_text}`\n\n"
    text += "Please reply to this message with your edited text (max 500 characters)."
    
    if context_id not in _pending_responses:
        _pending_responses[context_id] = {
            'event': threading.Event(),
            'result': None,
            'waiting_for_text': True
        }
    else:
        _pending_responses[context_id]['waiting_for_text'] = True
    
    return await _send_message(text)


async def _send_single_reply_edit(reply_num, reply_text, context_id):
    """Send single reply edit request."""
    text = f"📝 *Edit Reply {reply_num}*\n\n"
    text += f"Current text:\n`{reply_text}`\n\n"
    text += "Please reply to this message with your edited text (max 500 characters)."
    
    if context_id not in _pending_responses:
        _pending_responses[context_id] = {
            'event': threading.Event(),
            'result': None,
            'waiting_for_text': True
        }
    
    return await _send_message(text)


def _wait_for_response(context_id, timeout=300):
    """Wait for user response (synchronous wrapper using threading.Event)."""
    if context_id not in _pending_responses:
        _pending_responses[context_id] = {
            'event': threading.Event(),  # Use threading.Event, not asyncio.Event
            'result': None,
            'waiting_for_text': False
        }
    
    # Wait for the event (blocking, thread-safe)
    # Use polling approach for timeout compatibility
    event = _pending_responses[context_id]['event']
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        if event.is_set():
            result = _pending_responses[context_id].get('result')
            del _pending_responses[context_id]
            return result
        time.sleep(0.1)  # Poll every 100ms
    
    # Timeout
    if context_id in _pending_responses:
        del _pending_responses[context_id]
    return None


# Public synchronous functions
def send_post_preview(post_content, image_path=None):
    """Send post preview and wait for response."""
    _start_bot()
    
    context_id = str(uuid.uuid4())
    _pending_responses[context_id] = {
        'event': threading.Event(),  # Use threading.Event
        'result': None,
        'post_content': post_content
    }
    
    preview_text = f"📝 *New Post Preview*\n\n"
    preview_text += f"{post_content}\n\n"
    preview_text += f"📊 Length: {len(post_content)} characters"
    
    if len(post_content) > 500:
        preview_text += f" ⚠️ (exceeds 500 limit)"
    
    if image_path and os.path.exists(image_path):
        preview_text += "\n📷 Image included"
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"approve_post_{context_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject_post_{context_id}"),
            InlineKeyboardButton("✏️ Edit", callback_data=f"edit_post_{context_id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Send message using bot's event loop
    _send_message_sync(preview_text, reply_markup=reply_markup, photo_path=image_path)
    
    return _wait_for_response(context_id)


def send_edit_options(post_content):
    """Send edit options and wait for response."""
    _start_bot()
    
    context_id = str(uuid.uuid4())
    _pending_responses[context_id] = {
        'event': threading.Event(),  # Use threading.Event
        'result': None,
        'post_content': post_content,
        'waiting_for_text': False
    }
    
    text = "✏️ *What would you like to edit?*"
    keyboard = [
        [
            InlineKeyboardButton("📝 Edit Text", callback_data=f"edit_text_{context_id}"),
            InlineKeyboardButton("🖼️ New Image", callback_data=f"edit_image_{context_id}")
        ],
        [
            InlineKeyboardButton("📝🖼️ Both", callback_data=f"edit_both_{context_id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Send message using sync helper
    _send_message_sync(text, reply_markup=reply_markup)
    
    response = _wait_for_response(context_id)
    
    # If response is "edit_text" or "edit_both", we need to wait for the actual text
    if response == "edit_text":
        # The callback handler should have already sent the text edit request
        # Now wait for the text reply (use same context_id)
        edited_text = _wait_for_response(context_id, timeout=600)  # Longer timeout for text input
        return edited_text if edited_text else "edit_text"
    elif response == "edit_both":
        # First wait for text edit - the callback handler sent the text edit request
        # Create a new context for the text response
        text_edit_context = f"{context_id}_text"
        _pending_responses[text_edit_context] = {
            'event': threading.Event(),
            'result': None,
            'waiting_for_text': True
        }
        # Wait for the text reply
        edited_text = _wait_for_response(text_edit_context, timeout=600)
        if edited_text and len(edited_text) > 0:
            # Store the edited text in the original context for the main code to access
            if context_id in _pending_responses:
                _pending_responses[context_id]['edited_text'] = edited_text
            return "edit_both"  # Return this so main code knows to generate image too
        return "edit_both"
    
    return response


def send_replies_preview(replies, posts):
    """Send replies preview and wait for response."""
    context_id = str(uuid.uuid4())
    _pending_responses[context_id] = {
        'event': threading.Event(),  # Use threading.Event
        'result': None,
        'replies': replies
    }
    
    text = f"💬 *Generated Replies*\n\n"
    for i, reply in enumerate(replies, 1):
        post_num = reply.get('post_number', 0)
        reply_text = reply.get('reply_text', '')
        if 1 <= post_num <= len(posts):
            post = posts[post_num - 1]
            text += f"*Reply {i}* (to @{post['author']}):\n{reply_text}\n\n"
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Post All", callback_data=f"approve_replies_all_{context_id}"),
            InlineKeyboardButton("❌ Reject All", callback_data=f"reject_replies_{context_id}")
        ],
        [
            InlineKeyboardButton("✏️ Select & Edit", callback_data=f"edit_replies_{context_id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Send message using bot's event loop
    _send_message_sync(text, reply_markup=reply_markup)
    
    return _wait_for_response(context_id)


def send_reply_selection(replies, posts):
    """Send reply selection for editing."""
    context_id = str(uuid.uuid4())
    _pending_responses[context_id] = {
        'event': asyncio.Event(),
        'result': None,
        'replies': replies
    }
    
    text = "✏️ *Select replies to edit:*\n\n"
    keyboard = []
    for i, reply in enumerate(replies, 1):
        post_num = reply.get('post_number', 0)
        if 1 <= post_num <= len(posts):
            post = posts[post_num - 1]
            keyboard.append([
                InlineKeyboardButton(
                    f"Reply {i} (to @{post['author']})",
                    callback_data=f"edit_reply_{i}_{context_id}"
                )
            ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    # Send message using bot's event loop
    _send_message_sync(text, reply_markup=reply_markup)
    
    return _wait_for_response(context_id)


def send_confirmation(message_text):
    """Send a confirmation message."""
    _send_message_sync(message_text)


def send_mode_selection():
    """Send mode selection and wait for response."""
    _start_bot()
    
    context_id = "mode_selection"
    _pending_responses[context_id] = {
        'event': asyncio.Event(),
        'result': None
    }
    
    text = "🤖 *Mastodon Post Generator*\n\nWhat would you like to do?"
    keyboard = [
        [
            InlineKeyboardButton("📝 New Post", callback_data="mode_new_post"),
            InlineKeyboardButton("💬 Craft Replies", callback_data="mode_craft_replies")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Send message using bot's event loop
    _send_message_sync(text, reply_markup=reply_markup)
    
    return _wait_for_response(context_id)


def wait_for_text_edit(current_text):
    """Send text edit request and wait for user's reply."""
    _start_bot()
    
    context_id = str(uuid.uuid4())
    _pending_responses[context_id] = {
        'event': asyncio.Event(),
        'result': None,
        'waiting_for_text': True
    }
    
    _send_message_sync_async(_send_text_edit_request(context_id, current_text))
    
    return _wait_for_response(context_id)
