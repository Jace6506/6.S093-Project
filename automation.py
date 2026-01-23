"""Automation listeners for auto-posting and auto-replying."""
import os
import time
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from config import mastodon, notion
from notion import fetch_notion_page_content, fetch_notion_database_pages
from mastodon_api import post_to_mastodon, reply_to_post, search_mastodon_posts
from modes import create_new_post_mode
from llm import generate_post_with_rag, generate_replies_to_posts
from rag_retrieval import retrieve_context, embed_notion_content
from rag_database import check_content_embedded
from database import create_post, get_posts, init_database
from rag_database import init_rag_database
import tempfile

# Ensure databases are initialized
init_database()
init_rag_database()


class AutomationListener:
    """Background service for automated posting and replying."""
    
    def __init__(self):
        self.running = False
        self.last_notion_check = {}
        self.last_mastodon_check = None
        self.processed_notifications = set()
        
    async def start(self):
        """Start the automation listeners."""
        self.running = True
        print("🤖 Automation listeners started")
        print("   - Notion page update listener (Part 4)")
        print("   - Mastodon notifications listener (Part 5)")
        
        # Run both listeners concurrently
        asyncio.create_task(self.notion_listener_loop())
        asyncio.create_task(self.mastodon_listener_loop())
    
    def stop(self):
        """Stop the automation listeners."""
        self.running = False
        print("🛑 Automation listeners stopped")
    
    async def notion_listener_loop(self):
        """Part 4: Auto-create posts when Notion pages are updated."""
        check_interval = int(os.getenv("NOTION_CHECK_INTERVAL", "300"))  # Default 5 minutes
        
        while self.running:
            try:
                await self.check_notion_updates()
                await asyncio.sleep(check_interval)
            except Exception as e:
                print(f"❌ Error in Notion listener: {e}")
                await asyncio.sleep(60)  # Wait 1 minute before retrying
    
    async def mastodon_listener_loop(self):
        """Part 5: Auto-reply to Mastodon comments/mentions."""
        check_interval = int(os.getenv("MASTODON_CHECK_INTERVAL", "60"))  # Default 1 minute
        
        while self.running:
            try:
                await self.check_mastodon_notifications()
                await asyncio.sleep(check_interval)
            except Exception as e:
                print(f"❌ Error in Mastodon listener: {e}")
                await asyncio.sleep(60)  # Wait 1 minute before retrying
    
    async def check_notion_updates(self):
        """Check for Notion page updates and auto-create posts."""
        NOTION_DATABASE_ID = os.environ.get("NOTION_DATABASE_ID", "")
        NOTION_PAGE_ID = os.environ.get("NOTION_PAGE_ID", "")
        
        if not NOTION_DATABASE_ID and not NOTION_PAGE_ID:
            return
        
        try:
            # Get pages to check
            pages_to_check = []
            
            if NOTION_DATABASE_ID:
                # Get pages from database
                results = notion.databases.query(NOTION_DATABASE_ID)
                for page in results.get("results", []):
                    pages_to_check.append({
                        "id": page["id"],
                        "last_edited": page.get("last_edited_time", "")
                    })
            elif NOTION_PAGE_ID:
                # Get individual pages
                page_ids = [pid.strip() for pid in NOTION_PAGE_ID.split(",") if pid.strip()]
                for page_id in page_ids:
                    try:
                        page = notion.pages.retrieve(page_id)
                        pages_to_check.append({
                            "id": page["id"],
                            "last_edited": page.get("last_edited_time", "")
                        })
                    except Exception as e:
                        print(f"⚠️  Could not fetch page {page_id}: {e}")
            
            # Check for updates
            for page_info in pages_to_check:
                page_id = page_info["id"]
                last_edited = page_info["last_edited"]
                
                # Check if this page was updated since last check
                if page_id in self.last_notion_check:
                    if last_edited <= self.last_notion_check[page_id]:
                        continue  # No update
                
                # Page was updated - create a post
                print(f"📝 Notion page {page_id} was updated. Creating post...")
                await self.auto_create_post_from_notion(page_id)
                
                # Update last check time
                self.last_notion_check[page_id] = last_edited
                
        except Exception as e:
            print(f"❌ Error checking Notion updates: {e}")
    
    async def auto_create_post_from_notion(self, page_id: str):
        """Automatically create and post from a Notion page update."""
        try:
            # Re-embed content if needed
            if not check_content_embedded("notion_page", page_id):
                print("   Embedding updated content...")
                embed_notion_content(force_reembed=False)
            
            # Use RAG to generate post
            query = "services and offerings"  # Default query
            rag_context, results = retrieve_context(query, top_k=10)
            
            if not rag_context or rag_context == "No relevant context found.":
                print("   ⚠️  No RAG context found, skipping auto-post")
                return
            
            # Generate post using RAG
            from llm import generate_post_with_rag
            post_content = generate_post_with_rag(rag_context, topic=query)
            
            # Truncate if needed
            if len(post_content) > 500:
                from utils import truncate_post_to_limit
                post_content = truncate_post_to_limit(post_content, max_length=500)
            
            # Optionally generate image (if configured)
            image_path = None
            from config import replicate_client, REPLICATE_MODEL
            if replicate_client and REPLICATE_MODEL:
                try:
                    from llm import generate_image_prompt_from_post
                    from replicate_api import generate_image_with_replicate, download_image
                    
                    image_prompt = generate_image_prompt_from_post(post_content)
                    image_url = generate_image_with_replicate(image_prompt)
                    
                    if image_url:
                        temp_image = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
                        temp_image.close()
                        image_path = download_image(image_url, temp_image.name)
                except Exception as e:
                    print(f"   ⚠️  Could not generate image: {e}")
            
            # Post to Mastodon
            print(f"   📤 Posting to Mastodon...")
            status = post_to_mastodon(post_content, image_path)
            
            if status:
                # Save to database
                from database import update_post
                post_id = create_post(
                    content=post_content,
                    tags=None,
                    notion_page_id=page_id,
                    status="published"
                )
                # Update post with Mastodon URL
                if post_id and status:
                    update_post(
                        post_id=post_id,
                        mastodon_post_id=str(status.get("id", "")),
                        status="published"
                    )
                print(f"   ✅ Auto-posted successfully! URL: {status.get('url', 'N/A')}")
                
                # Clean up temp image
                if image_path and os.path.exists(image_path):
                    try:
                        os.unlink(image_path)
                    except:
                        pass
            else:
                print(f"   ❌ Failed to auto-post")
                
        except Exception as e:
            print(f"   ❌ Error auto-creating post: {e}")
    
    async def check_mastodon_notifications(self):
        """Check for Mastodon notifications and auto-reply."""
        if not mastodon:
            return
        
        try:
            # Get notifications (mentions, replies, etc.)
            notifications = mastodon.notifications(limit=20)
            
            for notification in notifications:
                notification_id = notification.get("id")
                
                # Skip if already processed
                if notification_id in self.processed_notifications:
                    continue
                
                notification_type = notification.get("type")
                
                # Only handle mentions and replies
                if notification_type in ["mention", "status"]:
                    status = notification.get("status")
                    if not status:
                        continue
                    
                    # Get the account that mentioned/replied
                    account = notification.get("account", {})
                    username = account.get("username", "")
                    
                    # Get the status content
                    status_content = status.get("content", "")
                    # Remove HTML tags
                    import re
                    status_content = re.sub(r'<[^>]+>', '', status_content)
                    status_content = re.sub(r'&nbsp;', ' ', status_content)
                    status_content = re.sub(r'&amp;', '&', status_content)
                    
                    status_id = status.get("id")
                    in_reply_to_id = status.get("in_reply_to_id")
                    
                    print(f"💬 New Mastodon {notification_type} from @{username}")
                    print(f"   Content: {status_content[:100]}...")
                    
                    # Auto-reply
                    await self.auto_reply_to_notification(
                        status_id=status_id,
                        status_content=status_content,
                        username=username,
                        in_reply_to_id=in_reply_to_id
                    )
                    
                    # Mark as processed
                    self.processed_notifications.add(notification_id)
                    
                    # Limit processed notifications set size
                    if len(self.processed_notifications) > 1000:
                        # Keep only recent 500
                        self.processed_notifications = set(list(self.processed_notifications)[-500:])
            
        except Exception as e:
            print(f"❌ Error checking Mastodon notifications: {e}")
    
    async def auto_reply_to_notification(
        self,
        status_id: str,
        status_content: str,
        username: str,
        in_reply_to_id: Optional[str] = None
    ):
        """Automatically generate and post a reply to a Mastodon notification."""
        try:
            # Get business context from Notion (optional)
            business_context = ""
            NOTION_DATABASE_ID = os.environ.get("NOTION_DATABASE_ID", "")
            NOTION_PAGE_ID = os.environ.get("NOTION_PAGE_ID", "")
            
            try:
                if NOTION_DATABASE_ID:
                    business_context = fetch_notion_database_pages(NOTION_DATABASE_ID, max_pages=3)
                elif NOTION_PAGE_ID:
                    page_ids = [pid.strip() for pid in NOTION_PAGE_ID.split(",") if pid.strip()]
                    if len(page_ids) > 1:
                        from notion import fetch_multiple_notion_pages
                        business_context = fetch_multiple_notion_pages(page_ids)
                    else:
                        business_context = fetch_notion_page_content(page_ids[0])
            except Exception as e:
                print(f"   ⚠️  Could not fetch Notion context: {e}")
            
            # Create a post object for the reply generation function
            original_post = {
                "id": status_id,
                "content": status_content,
                "author": username,
                "url": f"https://mastodon.social/@{username}/{status_id}"  # Approximate URL
            }
            
            # Generate reply
            from llm import generate_replies_to_posts
            replies = generate_replies_to_posts([original_post], business_context)
            
            if not replies or len(replies) == 0:
                print(f"   ⚠️  Could not generate reply")
                return
            
            reply_text = replies[0].get("reply_text", "")
            
            if not reply_text or len(reply_text.strip()) == 0:
                print(f"   ⚠️  Generated empty reply")
                return
            
            # Truncate if needed
            if len(reply_text) > 500:
                from utils import truncate_post_to_limit
                reply_text = truncate_post_to_limit(reply_text, max_length=500)
            
            # Post reply
            print(f"   📤 Posting reply...")
            status = reply_to_post(status_id, reply_text)
            
            if status:
                print(f"   ✅ Auto-replied successfully! URL: {status.get('url', 'N/A')}")
            else:
                print(f"   ❌ Failed to auto-reply")
                
        except Exception as e:
            print(f"   ❌ Error auto-replying: {e}")


# Global instance
_automation_listener = None


def get_automation_listener() -> AutomationListener:
    """Get or create the global automation listener instance."""
    global _automation_listener
    if _automation_listener is None:
        _automation_listener = AutomationListener()
    return _automation_listener


async def start_automation():
    """Start the automation listeners and keep running."""
    listener = get_automation_listener()
    await listener.start()
    
    # Keep the service running indefinitely
    # The listeners run in background tasks, so we just wait here
    try:
        while listener.running:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        listener.stop()


def stop_automation():
    """Stop the automation listeners."""
    listener = get_automation_listener()
    listener.stop()
