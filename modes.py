"""Main workflow modes."""
import os
import tempfile
from config import mastodon, replicate_client, REPLICATE_MODEL
from notion import (
    fetch_notion_database_pages,
    fetch_multiple_notion_pages,
    fetch_notion_page_content
)
from llm import (
    generate_mastodon_post,
    generate_post_with_rag,
    generate_replies_to_posts,
    generate_image_prompt_from_post
)
from mastodon_api import (
    search_mastodon_posts,
    reply_to_post,
    post_to_mastodon
)
from replicate_api import (
    generate_image_with_replicate,
    download_image
)
from utils import (
    truncate_post_to_limit,
    edit_post_content
)
from telegram_interactive import (
    send_post_preview,
    send_edit_options,
    send_replies_preview,
    send_reply_selection,
    send_confirmation,
    wait_for_text_edit
)
from rag_retrieval import retrieve_context, embed_notion_content
from rag_database import check_content_embedded


def create_new_post_mode(use_rag: bool = True, topic: str = None):
    """
    Handle the 'create new post' workflow with optional RAG.
    
    Args:
        use_rag: If True, use RAG retrieval instead of full content
        topic: Optional topic/query for RAG retrieval
    """
    # Configuration
    NOTION_DATABASE_ID = os.environ.get("NOTION_DATABASE_ID", "")
    NOTION_PAGE_ID = os.environ.get("NOTION_PAGE_ID", "")
    
    rag_context = None
    query = None
    
    # Ensure content is embedded if using RAG
    if use_rag:
        print("=" * 50)
        print("RAG Mode: Checking embeddings...")
        print("=" * 50)
        
        # Check if content needs to be embedded
        needs_embedding = False
        if NOTION_DATABASE_ID:
            if not check_content_embedded("notion_database", NOTION_DATABASE_ID):
                needs_embedding = True
        elif NOTION_PAGE_ID:
            page_ids = [pid.strip() for pid in NOTION_PAGE_ID.split(",") if pid.strip()]
            for page_id in page_ids:
                if not check_content_embedded("notion_page", page_id):
                    needs_embedding = True
                    break
        
        if needs_embedding:
            print("Content not yet embedded. Embedding now...")
            chunks_embedded = embed_notion_content(force_reembed=False)
            print(f"Embedded {chunks_embedded} chunks")
        else:
            print("Content already embedded. Using existing embeddings.")
        
        # Retrieve relevant context using RAG
        print(f"\n{'='*50}")
        print("Retrieving relevant context with RAG...")
        print("=" * 50)
        
        # Use topic if provided, otherwise use a generic query that should match any content
        query = topic if topic else "services and offerings"
        print(f"Search query: {query}")
        
        rag_context, results = retrieve_context(query, top_k=10)
        print(f"Retrieved {len(results)} relevant chunks")
        
        if not rag_context or rag_context == "No relevant context found.":
            print("⚠️  No relevant context found. Falling back to full content mode.")
            use_rag = False
            rag_context = None
        else:
            print(f"Context length: {len(rag_context)} characters")
    
    # Generate Mastodon post text
    print(f"\n{'='*50}")
    print("Generating Mastodon post...")
    print(f"{'='*50}\n")
    
    if use_rag and rag_context:
        # Use RAG context
        post_content = generate_post_with_rag(rag_context, topic=query)
    else:
        # Fallback to full content mode
        if NOTION_DATABASE_ID:
            print("Fetching content from Notion database...")
            content = fetch_notion_database_pages(NOTION_DATABASE_ID, max_pages=5)
        elif NOTION_PAGE_ID:
            page_ids = [pid.strip() for pid in NOTION_PAGE_ID.split(",") if pid.strip()]
            if len(page_ids) > 1:
                print(f"Fetching content from {len(page_ids)} Notion pages...")
                content = fetch_multiple_notion_pages(page_ids)
            else:
                print("Fetching content from Notion page...")
                content = fetch_notion_page_content(page_ids[0])
        else:
            print("Error: Please set either NOTION_DATABASE_ID or NOTION_PAGE_ID environment variable")
            exit(1)
        
        print(f"\nFetched {len(content)} characters from Notion\n")
        post_content = generate_mastodon_post(content)
    
    # Generate image for the post
    image_path = None
    if replicate_client and REPLICATE_MODEL:
        print(f"\n{'='*50}")
        print("Generating image for post...")
        print(f"{'='*50}\n")
        
        # Generate image prompt from post text
        image_prompt = generate_image_prompt_from_post(post_content)
        print(f"Image prompt: {image_prompt}\n")
        
        # Generate image
        image_url = generate_image_with_replicate(image_prompt)
        
        if image_url:
            # Download image to temp file
            temp_image = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
            temp_image.close()
            image_path = download_image(image_url, temp_image.name)
            
            if image_path:
                print(f"✅ Image generated and saved: {image_path}")
            else:
                print("⚠️  Could not download image")
        else:
            print("⚠️  Could not generate image")
    else:
        print("⚠️  Replicate not configured. Posting without image.")
        print("   Set REPLICATE_API_TOKEN and REPLICATE_MODEL to enable image generation")
    
    # Warn if over limit
    if len(post_content) > 500:
        post_content = truncate_post_to_limit(post_content, max_length=500)
        print(f"⚠️  Post truncated to {len(post_content)} characters")
    
    # Loop until user posts or cancels
    while True:
        # Send preview to Telegram and wait for response
        if mastodon:
            response = send_post_preview(post_content, image_path)
            
            if response == "approve":
                # Final validation before posting
                if len(post_content) > 500:
                    post_content = truncate_post_to_limit(post_content, max_length=500)
                
                print("\nPosting to Mastodon...")
                status = post_to_mastodon(post_content, image_path)
                
                if status:
                    send_confirmation(f"✅ *Successfully posted to Mastodon!*\n\nPost URL: {status.get('url', 'N/A')}")
                    print(f"✅ Successfully posted to Mastodon!")
                    print(f"   Post URL: {status.get('url', 'N/A')}")
                    # Clean up temp image file
                    if image_path and os.path.exists(image_path):
                        try:
                            os.unlink(image_path)
                        except:
                            pass
                else:
                    send_confirmation("❌ *Failed to post to Mastodon*")
                    print("❌ Failed to post to Mastodon")
                break  # Exit the loop
                
            elif response == "reject":
                send_confirmation("❌ *Post rejected. Not published.*")
                print("Post not published. Exiting.")
                # Clean up temp image file
                if image_path and os.path.exists(image_path):
                    try:
                        os.unlink(image_path)
                    except:
                        pass
                break  # Exit the loop
                
            elif response == "edit":
                # Ask what they want to edit via Telegram
                edit_choice = send_edit_options(post_content)
                
                if edit_choice and edit_choice not in ["edit_text", "edit_image", "edit_both"]:
                    # This is edited text from edit_text option
                    post_content = edit_choice
                    if len(post_content) > 500:
                        post_content = truncate_post_to_limit(post_content, max_length=500)
                    # Loop will continue and show updated preview
                    
                elif edit_choice == "edit_image":
                    # Generate new image
                    if replicate_client and REPLICATE_MODEL:
                        send_confirmation("🖼️ *Generating new image...*")
                        image_prompt = generate_image_prompt_from_post(post_content)
                        
                        image_url = generate_image_with_replicate(image_prompt)
                        if image_url:
                            # Delete old image if exists
                            if image_path and os.path.exists(image_path):
                                try:
                                    os.unlink(image_path)
                                except:
                                    pass
                            
                            # Download new image
                            temp_image = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
                            temp_image.close()
                            image_path = download_image(image_url, temp_image.name)
                            
                            if image_path:
                                send_confirmation("✅ *New image generated!*")
                            else:
                                send_confirmation("⚠️ *Could not download new image*")
                        else:
                            send_confirmation("⚠️ *Could not generate new image*")
                    else:
                        send_confirmation("⚠️ *Replicate not configured*")
                        
                elif edit_choice == "edit_both":
                    # The text edit should have already happened in send_edit_options
                    # Now we need to get the edited text and generate new image
                    # Check if we have the edited text stored
                    from telegram_interactive import _pending_responses
                    context_id = None
                    for cid, pending in list(_pending_responses.items()):
                        if 'edited_text' in pending:
                            post_content = pending['edited_text']
                            context_id = cid
                            break
                    
                    if context_id and context_id in _pending_responses:
                        del _pending_responses[context_id]
                    
                    if len(post_content) > 500:
                        post_content = truncate_post_to_limit(post_content, max_length=500)
                    
                    # Then generate new image based on updated text
                    if replicate_client and REPLICATE_MODEL:
                        send_confirmation("🖼️ *Generating new image based on updated text...*")
                        image_prompt = generate_image_prompt_from_post(post_content)
                        
                        image_url = generate_image_with_replicate(image_prompt)
                        if image_url:
                            # Delete old image if exists
                            if image_path and os.path.exists(image_path):
                                try:
                                    os.unlink(image_path)
                                except:
                                    pass
                            
                            # Download new image
                            temp_image = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
                            temp_image.close()
                            image_path = download_image(image_url, temp_image.name)
                            
                            if image_path:
                                send_confirmation("✅ *Both text and image updated!*")
                            else:
                                send_confirmation("⚠️ *Could not download new image*")
                        else:
                            send_confirmation("⚠️ *Could not generate new image*")
                    else:
                        send_confirmation("⚠️ *Replicate not configured*")
                
                # Loop will continue and show updated preview
            else:
                # Timeout or no response
                send_confirmation("⏱️ *No response received. Exiting.*")
                if image_path and os.path.exists(image_path):
                    try:
                        os.unlink(image_path)
                    except:
                        pass
                break
        else:
            print("\n💡 To post to Mastodon, set these environment variables:")
            print("   - MASTODON_INSTANCE_URL (e.g., https://mastodon.social)")
            print("   - MASTODON_ACCESS_TOKEN (your Mastodon access token)")
            break


def craft_replies_mode():
    """Handle the 'craft replies' workflow."""
    if not mastodon:
        print("❌ Mastodon credentials not configured.")
        print("   Set MASTODON_INSTANCE_URL and MASTODON_ACCESS_TOKEN to use this feature.")
        return
    
    print("\n" + "=" * 50)
    print("CRAFT REPLIES MODE")
    print("=" * 50)
    
    # Get keyword from user (still use terminal for initial input)
    keyword = input("\nEnter a keyword to search for posts: ").strip()
    if not keyword:
        print("No keyword provided. Exiting.")
        return
    
    # Get optional business context (could be from Notion or user input)
    use_notion_context = input("Do you want to use your Notion content as context? (yes/no): ").strip().lower()
    business_context = ""
    
    if use_notion_context in ['yes', 'y']:
        # Fetch Notion content for context
        NOTION_DATABASE_ID = os.environ.get("NOTION_DATABASE_ID", "")
        NOTION_PAGE_ID = os.environ.get("NOTION_PAGE_ID", "")
        MAX_PAGES = 5
        
        try:
            if NOTION_DATABASE_ID:
                print("Fetching context from Notion database...")
                business_context = fetch_notion_database_pages(NOTION_DATABASE_ID, max_pages=MAX_PAGES)
            elif NOTION_PAGE_ID:
                page_ids = [pid.strip() for pid in NOTION_PAGE_ID.split(",") if pid.strip()]
                if len(page_ids) > 1:
                    business_context = fetch_multiple_notion_pages(page_ids)
                else:
                    business_context = fetch_notion_page_content(page_ids[0])
            print("Context loaded from Notion.")
        except Exception as e:
            print(f"⚠️  Could not fetch Notion context: {e}")
    
    # Search for posts
    print(f"\nSearching for posts containing '{keyword}'...")
    posts = search_mastodon_posts(keyword, limit=5)
    
    if not posts:
        print(f"❌ No posts found for keyword '{keyword}'")
        return
    
    print(f"\n✅ Found {len(posts)} posts:")
    print("-" * 50)
    for i, post in enumerate(posts, 1):
        print(f"\n{i}. @{post['author']}: {post['content'][:100]}...")
        print(f"   URL: {post['url']}")
    
    # Generate replies
    print(f"\n{'='*50}")
    print("Generating replies...")
    print("=" * 50)
    replies = generate_replies_to_posts(posts, business_context)
    
    if not replies:
        print("❌ Could not generate replies.")
        return
    
    # Display generated replies
    print("\n" + "=" * 50)
    print("GENERATED REPLIES")
    print("=" * 50)
    
    for reply in replies:
        post_num = reply.get('post_number', 0)
        reply_text = reply.get('reply_text', '')
        
        if 1 <= post_num <= len(posts):
            post = posts[post_num - 1]
            print(f"\n{'='*50}")
            print(f"Reply to Post {post_num}:")
            print(f"Original: @{post['author']} - {post['content'][:80]}...")
            print("-" * 50)
            print(f"Your reply ({len(reply_text)} chars):")
            print(reply_text)
            print("-" * 50)
    
    # Ask which replies to post via Telegram
    response = send_replies_preview(replies, posts)
    
    if response == "approve_all":
        # Post all replies
        send_confirmation("📤 *Posting all replies...*")
        print("\nPosting all replies...")
        for reply in replies:
            post_num = reply.get('post_number', 0)
            reply_text = reply.get('reply_text', '')
            
            if 1 <= post_num <= len(posts):
                post = posts[post_num - 1]
                print(f"\nPosting reply to Post {post_num}...")
                status = reply_to_post(post['id'], reply_text)
                if status:
                    send_confirmation(f"✅ *Reply {post_num} posted!*\nURL: {status.get('url', 'N/A')}")
                    print(f"✅ Reply posted! URL: {status.get('url', 'N/A')}")
                else:
                    send_confirmation(f"❌ *Failed to post reply {post_num}*")
                    print(f"❌ Failed to post reply")
    
    elif response == "edit_replies":
        # Let user select which ones to edit
        selected_response = send_reply_selection(replies, posts)
        
        # Handle individual reply editing
        # This is a simplified version - in production you'd want better state management
        if selected_response and selected_response.startswith("edit"):
            # Parse which reply was selected
            # For now, just show a message
            send_confirmation("✏️ *Reply editing selected. Please reply to the edit message with your new text.*")
            # In a full implementation, you'd handle the individual reply editing here
    
    elif response == "reject":
        send_confirmation("❌ *Replies rejected. No replies posted.*")
        print("No replies posted. Exiting.")
    
    else:
        send_confirmation("⏱️ *No response received. Exiting.*")
        print("No replies posted. Exiting.")
