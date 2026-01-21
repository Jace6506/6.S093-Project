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


def create_new_post_mode():
    """Handle the 'create new post' workflow."""
    # Configuration
    # Option 1: Fetch from a database (multiple pages)
    NOTION_DATABASE_ID = os.environ.get("NOTION_DATABASE_ID", "")
    MAX_PAGES = 5  # Adjust as needed
    
    # Option 2: Fetch from multiple page IDs (comma-separated)
    # Option 3: Fetch from a single page ID
    
    if NOTION_DATABASE_ID:
        print("Fetching content from Notion database...")
        content = fetch_notion_database_pages(NOTION_DATABASE_ID, max_pages=MAX_PAGES)
    else:
        # Check for multiple page IDs (comma-separated) or single page ID
        NOTION_PAGE_ID = os.environ.get("NOTION_PAGE_ID", "")
        if NOTION_PAGE_ID:
            # Check if multiple page IDs (comma-separated)
            page_ids = [pid.strip() for pid in NOTION_PAGE_ID.split(",") if pid.strip()]
            
            if len(page_ids) > 1:
                print(f"Fetching content from {len(page_ids)} Notion pages...")
                content = fetch_multiple_notion_pages(page_ids)
            else:
                print("Fetching content from Notion page...")
                content = fetch_notion_page_content(page_ids[0])
        else:
            print("Error: Please set either NOTION_DATABASE_ID or NOTION_PAGE_ID environment variable")
            print("For multiple pages, use comma-separated IDs: NOTION_PAGE_ID='id1,id2,id3'")
            exit(1)
    
    print(f"\nFetched {len(content)} characters from Notion\n")
    print("=" * 50)
    
    # Generate Mastodon post text
    print(f"\n{'='*50}")
    print("Generating Mastodon post...")
    print(f"{'='*50}\n")
    
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
    
    # Loop until user posts or cancels
    while True:
        print("\n" + "=" * 50)
        print("POST PREVIEW")
        print("=" * 50)
        print("\nText:")
        print("-" * 50)
        print(post_content)
        print("-" * 50)
        post_length = len(post_content)
        print(f"\nPost length: {post_length} characters")
        
        # Warn if over limit
        if post_length > 500:
            print(f"⚠️  WARNING: Post exceeds 500 character limit by {post_length - 500} characters!")
            print("   The post will be truncated before posting.")
            post_content = truncate_post_to_limit(post_content, max_length=500)
            print(f"   Truncated to {len(post_content)} characters")
        
        if image_path and os.path.exists(image_path):
            print(f"\n📷 Image: {image_path}")
            print("   (Image will be included with the post)")
        else:
            print("\n📷 No image")
        
        # Ask for confirmation before posting
        if mastodon:
            print("\n" + "=" * 50)
            response = input("Do you want to post this to Mastodon? (yes/no/edit): ").strip().lower()
            
            if response in ['yes', 'y']:
                # Final validation before posting
                if len(post_content) > 500:
                    post_content = truncate_post_to_limit(post_content, max_length=500)
                    print(f"\n⚠️  Post truncated to {len(post_content)} characters before posting")
                
                print("\nPosting to Mastodon...")
                status = post_to_mastodon(post_content, image_path)
                
                if status:
                    print(f"✅ Successfully posted to Mastodon!")
                    print(f"   Post URL: {status.get('url', 'N/A')}")
                    # Clean up temp image file
                    if image_path and os.path.exists(image_path):
                        try:
                            os.unlink(image_path)
                        except:
                            pass
                else:
                    print("❌ Failed to post to Mastodon")
                break  # Exit the loop
            elif response in ['edit', 'e']:
                # Ask what they want to edit
                print("\nWhat would you like to edit?")
                print("  1. Edit text")
                print("  2. Generate new image")
                print("  3. Both")
                
                edit_choice = input("Enter choice (1/2/3): ").strip()
                
                if edit_choice == "1":
                    # Edit text only
                    post_content = edit_post_content(post_content)
                    print("\n" + "=" * 50)
                    print("Text updated!")
                    print("=" * 50)
                elif edit_choice == "2":
                    # Generate new image
                    if replicate_client and REPLICATE_MODEL:
                        print("\nGenerating new image...")
                        image_prompt = generate_image_prompt_from_post(post_content)
                        print(f"Image prompt: {image_prompt}\n")
                        
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
                                print(f"✅ New image generated: {image_path}")
                            else:
                                print("⚠️  Could not download new image")
                        else:
                            print("⚠️  Could not generate new image")
                    else:
                        print("⚠️  Replicate not configured")
                elif edit_choice == "3":
                    # Edit both
                    post_content = edit_post_content(post_content)
                    
                    if replicate_client and REPLICATE_MODEL:
                        print("\nGenerating new image based on updated text...")
                        image_prompt = generate_image_prompt_from_post(post_content)
                        print(f"Image prompt: {image_prompt}\n")
                        
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
                                print(f"✅ New image generated: {image_path}")
                            else:
                                print("⚠️  Could not download new image")
                        else:
                            print("⚠️  Could not generate new image")
                    else:
                        print("⚠️  Replicate not configured")
                
                print("\n" + "=" * 50)
                print("Updated preview:")
                print("=" * 50)
                # Loop will continue and show the updated version
            else:
                print("Post not published. Exiting.")
                # Clean up temp image file
                if image_path and os.path.exists(image_path):
                    try:
                        os.unlink(image_path)
                    except:
                        pass
                break  # Exit the loop
    else:
        print("\n💡 To post to Mastodon, set these environment variables:")
        print("   - MASTODON_INSTANCE_URL (e.g., https://mastodon.social)")
        print("   - MASTODON_ACCESS_TOKEN (your Mastodon access token)")


def craft_replies_mode():
    """Handle the 'craft replies' workflow."""
    if not mastodon:
        print("❌ Mastodon credentials not configured.")
        print("   Set MASTODON_INSTANCE_URL and MASTODON_ACCESS_TOKEN to use this feature.")
        return
    
    print("\n" + "=" * 50)
    print("CRAFT REPLIES MODE")
    print("=" * 50)
    
    # Get keyword from user
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
    
    # Ask which replies to post
    print("\n" + "=" * 50)
    response = input("Which replies would you like to post? (all/select/none): ").strip().lower()
    
    if response in ['all', 'a']:
        # Post all replies
        print("\nPosting all replies...")
        for reply in replies:
            post_num = reply.get('post_number', 0)
            reply_text = reply.get('reply_text', '')
            
            if 1 <= post_num <= len(posts):
                post = posts[post_num - 1]
                print(f"\nPosting reply to Post {post_num}...")
                status = reply_to_post(post['id'], reply_text)
                if status:
                    print(f"✅ Reply posted! URL: {status.get('url', 'N/A')}")
                else:
                    print(f"❌ Failed to post reply")
    
    elif response in ['select', 's']:
        # Let user select which ones to post
        print("\nEnter the numbers of replies you want to post (comma-separated, e.g., 1,3,5):")
        selected = input().strip()
        
        try:
            selected_nums = [int(x.strip()) for x in selected.split(',')]
            for num in selected_nums:
                if 1 <= num <= len(replies):
                    reply = replies[num - 1]
                    post_num = reply.get('post_number', 0)
                    reply_text = reply.get('reply_text', '')
                    
                    if 1 <= post_num <= len(posts):
                        post = posts[post_num - 1]
                        print(f"\nPosting reply to Post {post_num}...")
                        status = reply_to_post(post['id'], reply_text)
                        if status:
                            print(f"✅ Reply posted! URL: {status.get('url', 'N/A')}")
                        else:
                            print(f"❌ Failed to post reply")
        except ValueError:
            print("Invalid selection. Exiting.")
    
    else:
        print("No replies posted. Exiting.")
