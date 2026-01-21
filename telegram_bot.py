"""Telegram bot integration for human-in-the-loop interactions."""
import os
import asyncio
import uuid
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from telegram.error import TelegramError


# Telegram configuration
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

# Global state management for pending actions
pending_actions = {}  # {context_id: {'type': 'post_approval', 'data': {...}, 'event': asyncio.Event, 'result': None}}


async def send_message(text, reply_markup=None, photo_path=None, chat_id=None):
    """Send a message to Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"⚠️  Telegram not configured. Would send: {text}")
        return None
    
    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        target_chat_id = int(chat_id or TELEGRAM_CHAT_ID)
        
        if photo_path and os.path.exists(photo_path):
            # Send photo with caption
            with open(photo_path, 'rb') as photo:
                message = await bot.send_photo(
                    chat_id=target_chat_id,
                    photo=photo,
                    caption=text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
        else:
            # Send text message
            message = await bot.send_message(
                chat_id=target_chat_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        
        return message
    except TelegramError as e:
        print(f"❌ Error sending Telegram message: {e}")
        return None
    except Exception as e:
        print(f"❌ Error: {e}")
        return None


async def send_post_preview(post_content, image_path=None, context_id=None):
    """Send post preview with approve/reject/edit buttons."""
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
    
    return await send_message(preview_text, reply_markup=reply_markup, photo_path=image_path)


async def send_edit_options(context_id):
    """Send edit options (text/image/both)."""
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
    
    return await send_message(text, reply_markup=reply_markup)


async def send_text_edit_request(context_id, current_text, message_id_to_reply=None):
    """Send request to edit text in Telegram."""
    text = f"📝 *Edit Text*\n\n"
    text += f"Current text:\n`{current_text}`\n\n"
    text += "Please reply to this message with your edited text (max 500 characters)."
    
    return await send_message(text)


async def send_replies_preview(replies, posts, context_id=None):
    """Send replies preview with approve/reject/edit buttons."""
    text = f"💬 *Generated Replies*\n\n"
    
    for i, reply in enumerate(replies, 1):
        post_num = reply.get('post_number', 0)
        reply_text = reply.get('reply_text', '')
        
        if 1 <= post_num <= len(posts):
            post = posts[post_num - 1]
            text += f"*Reply {i}* (to @{post['author']}):\n"
            text += f"{reply_text}\n\n"
    
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
    
    return await send_message(text, reply_markup=reply_markup)


async def send_reply_selection(replies, posts, context_id):
    """Send individual reply selection for editing."""
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
    return await send_message(text, reply_markup=reply_markup)


async def send_single_reply_edit(reply_num, reply_text, context_id):
    """Send a single reply for editing."""
    text = f"📝 *Edit Reply {reply_num}*\n\n"
    text += f"Current text:\n`{reply_text}`\n\n"
    text += "Please reply to this message with your edited text (max 500 characters)."
    
    return await send_message(text)


async def send_confirmation(message_text):
    """Send a confirmation message."""
    return await send_message(message_text)


async def wait_for_callback(context_id, timeout=300):
    """Wait for a callback response."""
    if context_id not in pending_actions:
        pending_actions[context_id] = {
            'event': asyncio.Event(),
            'result': None
        }
    
    try:
        await asyncio.wait_for(pending_actions[context_id]['event'].wait(), timeout=timeout)
        result = pending_actions[context_id].get('result')
        del pending_actions[context_id]
        return result
    except asyncio.TimeoutError:
        if context_id in pending_actions:
            del pending_actions[context_id]
        return None


def set_callback_result(context_id, result):
    """Set the result for a pending callback."""
    if context_id in pending_actions:
        pending_actions[context_id]['result'] = result
        pending_actions[context_id]['event'].set()


async def wait_for_text_reply(context_id, timeout=300):
    """Wait for a text reply from the user."""
    return await wait_for_callback(context_id, timeout)


def set_text_reply(context_id, text):
    """Set the text reply result."""
    set_callback_result(context_id, text)


def run_async(coro):
    """Run an async function synchronously."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)
