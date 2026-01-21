"""Telegram bot handler for processing callbacks and messages."""
import os
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram_bot import set_callback_result, set_text_reply, send_message, send_text_edit_request, send_single_reply_edit
from utils import truncate_post_to_limit

TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle callback query (button clicks)."""
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    chat_id = str(query.message.chat_id)
    
    # Only process if from the correct chat
    if chat_id != TELEGRAM_CHAT_ID:
        await query.edit_message_text("❌ Unauthorized")
        return
    
    # Parse callback data
    if callback_data.startswith("approve_post_"):
        context_id = callback_data.replace("approve_post_", "")
        await query.edit_message_text("✅ *APPROVED!* Posting to Mastodon...", parse_mode='Markdown')
        set_callback_result(context_id, "approve")
        
    elif callback_data.startswith("reject_post_"):
        context_id = callback_data.replace("reject_post_", "")
        await query.edit_message_text("❌ *REJECTED!* Post not published.", parse_mode='Markdown')
        set_callback_result(context_id, "reject")
        
    elif callback_data.startswith("edit_post_"):
        context_id = callback_data.replace("edit_post_", "")
        await query.edit_message_text("✏️ *Edit Mode*", parse_mode='Markdown')
        set_callback_result(context_id, "edit")
        
    elif callback_data.startswith("edit_text_"):
        context_id = callback_data.replace("edit_text_", "")
        # Get the current post content from context
        if context_id in context.user_data:
            current_text = context.user_data[context_id].get('post_content', '')
            await send_text_edit_request(context_id, current_text, query.message.message_id)
            set_callback_result(context_id, "edit_text")
        else:
            await query.edit_message_text("⚠️ Error: Could not find post content")
            
    elif callback_data.startswith("edit_image_"):
        context_id = callback_data.replace("edit_image_", "")
        await query.edit_message_text("🖼️ *Generating new image...*", parse_mode='Markdown')
        set_callback_result(context_id, "edit_image")
        
    elif callback_data.startswith("edit_both_"):
        context_id = callback_data.replace("edit_both_", "")
        if context_id in context.user_data:
            current_text = context.user_data[context_id].get('post_content', '')
            await send_text_edit_request(context_id, current_text, query.message.message_id)
        await query.edit_message_text("✏️ *Editing both text and image...*", parse_mode='Markdown')
        set_callback_result(context_id, "edit_both")
        
    elif callback_data.startswith("approve_replies_all_"):
        context_id = callback_data.replace("approve_replies_all_", "")
        await query.edit_message_text("✅ *APPROVED!* Posting all replies...", parse_mode='Markdown')
        set_callback_result(context_id, "approve_all")
        
    elif callback_data.startswith("reject_replies_"):
        context_id = callback_data.replace("reject_replies_", "")
        await query.edit_message_text("❌ *REJECTED!* No replies posted.", parse_mode='Markdown')
        set_callback_result(context_id, "reject")
        
    elif callback_data.startswith("edit_replies_"):
        context_id = callback_data.replace("edit_replies_", "")
        await query.edit_message_text("✏️ *Select replies to edit...*", parse_mode='Markdown')
        set_callback_result(context_id, "edit_replies")
        
    elif callback_data.startswith("edit_reply_"):
        # Format: edit_reply_{reply_num}_{context_id}
        parts = callback_data.replace("edit_reply_", "").split("_")
        reply_num = int(parts[0])
        context_id = "_".join(parts[1:])
        
        if context_id in context.user_data:
            replies = context.user_data[context_id].get('replies', [])
            if 1 <= reply_num <= len(replies):
                reply_text = replies[reply_num - 1].get('reply_text', '')
                await send_single_reply_edit(reply_num, reply_text, f"{context_id}_{reply_num}")
                set_callback_result(f"{context_id}_{reply_num}", "edit")
            else:
                await query.edit_message_text("⚠️ Error: Invalid reply number")
        else:
            await query.edit_message_text("⚠️ Error: Could not find replies")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages (for editing)."""
    message = update.message
    if not message or not message.text:
        return
    
    chat_id = str(message.chat_id)
    if chat_id != TELEGRAM_CHAT_ID:
        return
    
    text = message.text.strip()
    
    # Check if this is a reply to an edit request
    if message.reply_to_message:
        reply_text = message.reply_to_message.text or message.reply_to_message.caption or ""
        
        # Look for context IDs in pending actions
        # This is a simplified approach - in production you'd want better state management
        for context_id in list(context.user_data.keys()):
            if context_id.startswith("edit_"):
                # Validate and truncate if necessary
                if len(text) > 500:
                    text = truncate_post_to_limit(text, max_length=500)
                    await send_message(f"⚠️ Text truncated to {len(text)} characters (500 limit)")
                
                set_text_reply(context_id, text)
                await send_message(f"✅ Text updated! ({len(text)} characters)")
                return
    
    # Regular message - just echo for now
    await send_message(f"Received: {text}")


def setup_handlers(application):
    """Set up Telegram bot handlers."""
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
