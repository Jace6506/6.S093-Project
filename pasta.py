from openai import OpenAI
from notion_client import Client
from mastodon import Mastodon
import os
import re
import tempfile
import subprocess
import json
import replicate
import requests
from urllib.parse import urlparse

# Load environment variables from .env file if it exists
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed, skip loading .env file


# Initialize Notion client
notion = Client(auth=os.environ.get("NOTION_API_KEY"))

# Initialize OpenAI client (OpenRouter)
llm_client = OpenAI(
    api_key=os.environ["OPENROUTER_API_KEY"],
    base_url="https://openrouter.ai/api/v1",
)

# Initialize Mastodon client
MASTODON_INSTANCE_URL = os.environ.get("MASTODON_INSTANCE_URL", "").strip()
MASTODON_ACCESS_TOKEN = os.environ.get("MASTODON_ACCESS_TOKEN", "").strip()

# Format instance URL properly (remove trailing slash, ensure https)
if MASTODON_INSTANCE_URL:
    MASTODON_INSTANCE_URL = MASTODON_INSTANCE_URL.rstrip('/')
    if not MASTODON_INSTANCE_URL.startswith('http'):
        MASTODON_INSTANCE_URL = f"https://{MASTODON_INSTANCE_URL}"

if MASTODON_INSTANCE_URL and MASTODON_ACCESS_TOKEN:
    try:
        mastodon = Mastodon(
            access_token=MASTODON_ACCESS_TOKEN,
            api_base_url=MASTODON_INSTANCE_URL
        )
        # Test the connection by verifying credentials
        mastodon.account_verify_credentials()
    except Exception as e:
        print(f"⚠️  Warning: Could not initialize Mastodon client: {e}")
        print(f"   Instance URL: {MASTODON_INSTANCE_URL}")
        print("   Please check your MASTODON_INSTANCE_URL and MASTODON_ACCESS_TOKEN")
        mastodon = None
else:
    mastodon = None

# Initialize Replicate client
REPLICATE_API_TOKEN = os.environ.get("REPLICATE_API_TOKEN", "").strip()
REPLICATE_MODEL = os.environ.get("REPLICATE_MODEL", "").strip()  # e.g., "username/model-name:version"

if REPLICATE_API_TOKEN:
    os.environ["REPLICATE_API_TOKEN"] = REPLICATE_API_TOKEN
    replicate_client = replicate.Client(api_token=REPLICATE_API_TOKEN)
else:
    replicate_client = None


def extract_text_from_block(block):
    """Extract text content from a Notion block."""
    text_content = []
    
    if block.get("type") == "paragraph":
        for text in block["paragraph"]["rich_text"]:
            text_content.append(text["plain_text"])
    elif block.get("type") == "heading_1":
        for text in block["heading_1"]["rich_text"]:
            text_content.append(f"# {text['plain_text']}")
    elif block.get("type") == "heading_2":
        for text in block["heading_2"]["rich_text"]:
            text_content.append(f"## {text['plain_text']}")
    elif block.get("type") == "heading_3":
        for text in block["heading_3"]["rich_text"]:
            text_content.append(f"### {text['plain_text']}")
    elif block.get("type") == "bulleted_list_item":
        for text in block["bulleted_list_item"]["rich_text"]:
            text_content.append(f"- {text['plain_text']}")
    elif block.get("type") == "numbered_list_item":
        for text in block["numbered_list_item"]["rich_text"]:
            text_content.append(f"1. {text['plain_text']}")
    elif block.get("type") == "code":
        for text in block["code"]["rich_text"]:
            text_content.append(f"```\n{text['plain_text']}\n```")
    
    return "\n".join(text_content)


def fetch_notion_page_content(page_id):
    """Fetch all content from a Notion page."""
    content_parts = []
    
    # Get page title
    page = notion.pages.retrieve(page_id)
    if page.get("properties"):
        # Try to get title from properties
        for prop_name, prop_value in page["properties"].items():
            if prop_value.get("type") == "title":
                title_parts = prop_value.get("title", [])
                if title_parts:
                    title = "".join([t["plain_text"] for t in title_parts])
                    content_parts.append(f"# {title}\n")
    
    # Get all blocks from the page
    blocks = notion.blocks.children.list(page_id)
    
    for block in blocks["results"]:
        text = extract_text_from_block(block)
        if text:
            content_parts.append(text)
        
        # Handle nested blocks (e.g., children of blocks)
        if block.get("has_children"):
            child_blocks = notion.blocks.children.list(block["id"])
            for child_block in child_blocks["results"]:
                child_text = extract_text_from_block(child_block)
                if child_text:
                    content_parts.append(child_text)
    
    return "\n\n".join(content_parts)


def fetch_multiple_notion_pages(page_ids):
    """Fetch content from multiple Notion pages."""
    all_content = []
    
    for page_id in page_ids:
        page_id = page_id.strip()  # Remove any whitespace
        if page_id:
            content = fetch_notion_page_content(page_id)
            if content:
                all_content.append(content)
    
    return "\n\n---\n\n".join(all_content)


def fetch_notion_database_pages(database_id, max_pages=10):
    """Fetch pages from a Notion database."""
    all_content = []
    
    results = notion.databases.query(database_id)
    pages = results.get("results", [])[:max_pages]
    
    for page in pages:
        page_id = page["id"]
        content = fetch_notion_page_content(page_id)
        if content:
            all_content.append(content)
    
    return "\n\n---\n\n".join(all_content)


def truncate_post_to_limit(post_content, max_length=500):
    """Truncate post content to fit within character limit, preserving words."""
    if len(post_content) <= max_length:
        return post_content
    
    # Truncate to max_length, but try to end at a word boundary
    truncated = post_content[:max_length]
    # Find the last space before the limit
    last_space = truncated.rfind(' ')
    if last_space > max_length * 0.9:  # Only use word boundary if it's not too short
        truncated = truncated[:last_space]
    
    # Add ellipsis if truncated
    if len(truncated) < len(post_content):
        truncated = truncated.rstrip() + "..."
    
    return truncated


def generate_mastodon_post(notion_content):
    """Generate a Mastodon post based on Notion content."""
    
    system_prompt = """You are a social media content creator. Based on the provided documents, create an engaging Mastodon post.
    
Guidelines:
- Create a single, engaging Mastodon post (MUST be 500 characters or less - this is a hard limit)
- Make it shareable and engaging
- Use hashtags strategically (2-5 relevant hashtags)
- Maintain the key messages from the source material
- Write in a conversational, authentic tone
- Do NOT include any numbering or formatting like "1.", "2.", etc. - just write the post directly
- IMPORTANT: Keep your response under 500 characters total"""

    user_message = f"""Based on the following documents from Notion, create a Mastodon post (max 500 characters):

{notion_content}

Generate the post now (just the post text, no numbering or extra formatting, under 500 characters):"""

    response = llm_client.chat.completions.create(
        model="nvidia/nemotron-3-nano-30b-a3b:free",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
    )

    post_content = response.choices[0].message.content.strip()
    
    # Clean up any numbering or formatting the LLM might have added
    # Remove leading numbers like "1.", "2.", etc.
    post_content = re.sub(r'^\d+[\.\)]\s*', '', post_content, flags=re.MULTILINE)
    # Remove "Post:" or similar prefixes
    post_content = re.sub(r'^(Post|Mastodon Post|Here\'s the post):\s*', '', post_content, flags=re.IGNORECASE)
    post_content = post_content.strip()
    
    # Enforce 500 character limit
    if len(post_content) > 500:
        post_content = truncate_post_to_limit(post_content, max_length=500)
        print(f"⚠️  Post exceeded 500 characters and was truncated to {len(post_content)} characters")
    
    return post_content


def edit_post_content(post_content):
    """Allow user to edit the post content using their default editor."""
    # Create a temporary file with the current post content
    with tempfile.NamedTemporaryFile(mode='w+', suffix='.txt', delete=False) as tmp_file:
        tmp_file.write(post_content)
        tmp_file_path = tmp_file.name
    
    # Determine which editor to use
    editor = os.environ.get('EDITOR', 'nano')  # Default to nano if $EDITOR not set
    
    # On macOS, try to use a GUI editor if available, otherwise use nano
    if os.name == 'posix' and 'EDITOR' not in os.environ:
        # Try common editors in order of preference
        for possible_editor in ['nano', 'vim', 'vi', 'code', 'subl']:
            try:
                subprocess.run(['which', possible_editor], 
                             check=True, capture_output=True)
                editor = possible_editor
                break
            except subprocess.CalledProcessError:
                continue
    
    print(f"\nOpening editor ({editor})...")
    print("Make your edits, save, and close the editor when done.")
    print("-" * 50)
    
    # Open the file in the editor
    try:
        if editor in ['code', 'subl']:
            # For GUI editors, run in background
            subprocess.run([editor, tmp_file_path], check=True)
        else:
            # For terminal editors, run in foreground
            subprocess.run([editor, tmp_file_path], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error opening editor: {e}")
        print("Falling back to simple text input...")
        # Fallback: just ask for new content
        print("\nEnter your edited post (press Enter twice when done, max 500 characters):")
        lines = []
        while True:
            line = input()
            if line == "" and lines and lines[-1] == "":
                break
            lines.append(line)
        edited_content = "\n".join(lines[:-1])  # Remove the last empty line
        edited_content = edited_content.strip()
        os.unlink(tmp_file_path)
        
        # Validate and truncate if necessary
        if len(edited_content) > 500:
            print(f"\n⚠️  Warning: Edited post is {len(edited_content)} characters (exceeds 500 limit)")
            edited_content = truncate_post_to_limit(edited_content, max_length=500)
            print(f"   Truncated to {len(edited_content)} characters")
        
        return edited_content
    except FileNotFoundError:
        print(f"Editor '{editor}' not found. Using simple text input...")
        print("\nEnter your edited post (press Enter twice when done, max 500 characters):")
        lines = []
        while True:
            line = input()
            if line == "" and lines and lines[-1] == "":
                break
            lines.append(line)
        edited_content = "\n".join(lines[:-1])
        edited_content = edited_content.strip()
        os.unlink(tmp_file_path)
        
        # Validate and truncate if necessary
        if len(edited_content) > 500:
            print(f"\n⚠️  Warning: Edited post is {len(edited_content)} characters (exceeds 500 limit)")
            edited_content = truncate_post_to_limit(edited_content, max_length=500)
            print(f"   Truncated to {len(edited_content)} characters")
        
        return edited_content
    
    # Read the edited content
    try:
        with open(tmp_file_path, 'r') as f:
            edited_content = f.read().strip()
        os.unlink(tmp_file_path)  # Clean up temp file
        
        # Validate and truncate if necessary
        if len(edited_content) > 500:
            print(f"\n⚠️  Warning: Edited post is {len(edited_content)} characters (exceeds 500 limit)")
            edited_content = truncate_post_to_limit(edited_content, max_length=500)
            print(f"   Truncated to {len(edited_content)} characters")
        
        return edited_content
    except Exception as e:
        print(f"Error reading edited file: {e}")
        return post_content  # Return original if something went wrong


def search_mastodon_posts(keyword, limit=5):
    """Search for recent posts on Mastodon by keyword."""
    if not mastodon:
        print("⚠️  Mastodon credentials not configured.")
        return []
    
    try:
        # Search for posts containing the keyword
        # Note: search() doesn't accept limit parameter, so we slice results afterward
        search_results = mastodon.search(keyword, result_type='statuses')
        
        posts = []
        # Get statuses from results and limit to requested number
        statuses = search_results.get('statuses', [])[:limit]
        
        for status in statuses:
            # Get full status details
            status_id = status.get('id')
            status_content = status.get('content', '')
            # Remove HTML tags from content
            status_content = re.sub(r'<[^>]+>', '', status_content)
            status_content = re.sub(r'&nbsp;', ' ', status_content)
            status_content = re.sub(r'&amp;', '&', status_content)
            status_content = re.sub(r'&lt;', '<', status_content)
            status_content = re.sub(r'&gt;', '>', status_content)
            
            posts.append({
                'id': status_id,
                'content': status_content.strip(),
                'url': status.get('url', ''),
                'author': status.get('account', {}).get('username', ''),
                'author_display': status.get('account', {}).get('display_name', ''),
                'created_at': status.get('created_at', '')
            })
        
        return posts
    except Exception as e:
        print(f"❌ Error searching Mastodon: {e}")
        return []


def generate_replies_to_posts(posts, business_context=""):
    """Generate replies to multiple posts using structured outputs."""
    
    # Format posts for the LLM
    posts_text = ""
    for i, post in enumerate(posts, 1):
        posts_text += f"""
Post {i}:
Author: @{post['author']} ({post.get('author_display', '')})
Content: {post['content']}
URL: {post['url']}
---
"""
    
    system_prompt = """You are a helpful assistant that crafts engaging, authentic replies to social media posts.
Generate thoughtful replies that:
- Are concise and conversational (under 500 characters)
- Add value to the conversation
- Are authentic and personable
- Reference specific parts of the original post when relevant
- Include relevant hashtags if appropriate (1-3 max)

Return your replies as a JSON object with this exact structure:
{
  "replies": [
    {
      "post_number": 1,
      "reply_text": "Your reply text here"
    },
    {
      "post_number": 2,
      "reply_text": "Your reply text here"
    }
  ]
}

Make sure the JSON is valid and properly formatted."""
    
    context_note = f"\n\nBusiness Context: {business_context}\n" if business_context else ""
    
    user_message = f"""Here are posts I want to reply to:{context_note}

{posts_text}

Generate appropriate replies for all {len(posts)} posts. Return ONLY valid JSON with the structure specified above."""

    try:
        # Try with JSON mode first
        try:
            response = llm_client.chat.completions.create(
                model="nvidia/nemotron-3-nano-30b-a3b:free",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                response_format={"type": "json_object"}  # Structured output
            )
        except Exception as e:
            # If JSON mode not supported, try without it
            print(f"⚠️  JSON mode not supported, trying without...")
            response = llm_client.chat.completions.create(
                model="nvidia/nemotron-3-nano-30b-a3b:free",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ]
            )
        
        content = response.choices[0].message.content.strip()
        
        # Try to extract JSON from the response if it's wrapped in text
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            content = json_match.group(0)
        
        reply_data = json.loads(content)
        return reply_data.get('replies', [])
    except json.JSONDecodeError as e:
        print(f"❌ Error parsing JSON response: {e}")
        print(f"Raw response: {response.choices[0].message.content[:500]}")
        return []
    except Exception as e:
        print(f"❌ Error generating replies: {e}")
        return []


def reply_to_post(post_id, reply_text):
    """Reply to a specific Mastodon post."""
    if not mastodon:
        return None
    
    try:
        status = mastodon.status_post(reply_text, in_reply_to_id=post_id)
        return status
    except Exception as e:
        print(f"❌ Error replying to post: {e}")
        return None


def generate_image_prompt_from_post(post_text):
    """Generate an image generation prompt based on the post text."""
    system_prompt = """You are a prompt engineer for image generation. Based on a social media post, create a concise, descriptive prompt for generating a relevant image.
    
Guidelines:
- Keep the prompt under 100 words
- Focus on visual elements, mood, and setting
- Make it suitable for image generation
- Include the trigger word "jace" in the prompt
- Be specific about composition, lighting, and style
- Return ONLY the prompt, no explanation or extra text"""

    user_message = f"""Create an image generation prompt for this post:

{post_text}

Image prompt:"""

    try:
        response = llm_client.chat.completions.create(
            model="nvidia/nemotron-3-nano-30b-a3b:free",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        )
        
        prompt = response.choices[0].message.content.strip()
        # Ensure "jace" is in the prompt (the trigger word)
        if "jace" not in prompt.lower():
            prompt = f"jace, {prompt}"
        
        return prompt
    except Exception as e:
        print(f"⚠️  Error generating image prompt: {e}")
        # Fallback: use post text with trigger word
        return f"jace, {post_text[:200]}"


def generate_image_with_replicate(prompt):
    """Generate an image using Replicate."""
    if not replicate_client:
        print("⚠️  Replicate API not configured.")
        return None
    
    if not REPLICATE_MODEL:
        print("⚠️  REPLICATE_MODEL not set. Please set it in your .env file")
        print("   Example: REPLICATE_MODEL=username/model-name")
        print("   Or: REPLICATE_MODEL=username/model-name:version-id")
        return None
    
    try:
        print(f"   Generating image with prompt: {prompt[:100]}...")
        print("   This may take a minute...")
        print(f"   Using model: {REPLICATE_MODEL}")
        
        # Try different model formats
        model_to_use = REPLICATE_MODEL
        
        # If model has a colon, try it as-is first
        if ':' in REPLICATE_MODEL:
            try:
                output = replicate_client.run(
                    model_to_use,
                    input={"prompt": prompt}
                )
            except Exception as e:
                # If version fails, try without version (use latest)
                if "version" in str(e).lower() or "422" in str(e):
                    print(f"   ⚠️  Version issue, trying model without version...")
                    model_to_use = REPLICATE_MODEL.split(':')[0]
                    output = replicate_client.run(
                        model_to_use,
                        input={"prompt": prompt}
                    )
                else:
                    raise
        
        # If no colon, use as-is
        else:
            output = replicate_client.run(
                model_to_use,
                input={"prompt": prompt}
            )
        
        # Replicate returns a URL or list of URLs
        if isinstance(output, list):
            image_url = output[0] if output else None
        else:
            image_url = output
        
        if image_url:
            print(f"   ✅ Image generated successfully!")
            return image_url
        else:
            print("   ⚠️  No image URL returned")
            return None
            
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Error generating image: {error_msg}")
        
        # Provide helpful troubleshooting
        if "422" in error_msg or "version" in error_msg.lower() or "permission" in error_msg.lower():
            print("\n💡 Troubleshooting tips:")
            print("   1. Check your REPLICATE_MODEL format:")
            print("      - Try: username/model-name (without version)")
            print("      - Or: username/model-name:version-id")
            print(f"   2. Current model: {REPLICATE_MODEL}")
            print("   3. Make sure the model exists and you have access to it")
            print("   4. Check your Replicate dashboard: https://replicate.com/models")
            print("   5. For finetuned models, use: your-username/model-name")
        
        return None


def download_image(image_url, save_path):
    """Download an image from a URL to a local file."""
    try:
        response = requests.get(image_url, stream=True)
        response.raise_for_status()
        
        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        return save_path
    except Exception as e:
        print(f"❌ Error downloading image: {e}")
        return None


def post_to_mastodon(post_content, image_path=None):
    """Post content to Mastodon, optionally with an image."""
    if not mastodon:
        print("⚠️  Mastodon credentials not configured. Skipping post.")
        print("   Set MASTODON_INSTANCE_URL and MASTODON_ACCESS_TOKEN to enable posting.")
        return None
    
    # Final safety check - ensure post doesn't exceed 500 characters
    if len(post_content) > 500:
        print(f"⚠️  Post is {len(post_content)} characters, truncating to 500...")
        post_content = truncate_post_to_limit(post_content, max_length=500)
    
    try:
        # Verify credentials first
        account = mastodon.account_verify_credentials()
        print(f"   Authenticated as: @{account['username']}")
        
        # Post to Mastodon with or without media
        if image_path and os.path.exists(image_path):
            # Upload media first
            media = mastodon.media_post(image_path)
            # Post with media
            status = mastodon.status_post(post_content, media_ids=[media['id']])
        else:
            # Post without media
            status = mastodon.status_post(post_content)
        return status
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Error posting to Mastodon: {error_msg}")
        
        # Provide helpful error messages
        if "404" in error_msg or "Not Found" in error_msg:
            print("\n💡 Troubleshooting tips:")
            print("   1. Check that your MASTODON_INSTANCE_URL is correct")
            print("      Example: https://mastodon.social (no trailing slash)")
            print("   2. Verify your access token is valid and has 'write:statuses' scope")
            print("   3. Make sure the instance URL matches the instance where you created the token")
            print(f"   4. Current instance URL: {MASTODON_INSTANCE_URL}")
        elif "401" in error_msg or "Unauthorized" in error_msg:
            print("\n💡 Your access token may be invalid or expired.")
            print("   Generate a new token in Settings → Development")
        elif "403" in error_msg or "Forbidden" in error_msg:
            print("\n💡 Your access token may not have the required permissions.")
            print("   Make sure 'write:statuses' scope is enabled when creating the app")
        
        return None


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


# Main execution
if __name__ == "__main__":
    # Ask user which mode they want
    print("=" * 50)
    print("MASTODON POST GENERATOR")
    print("=" * 50)
    print("\nWhat would you like to do?")
    print("  1. Create a new post from Notion content")
    print("  2. Craft replies to existing posts")
    
    mode = input("\nEnter choice (1 or 2): ").strip()
    
    if mode == "1":
        create_new_post_mode()
    elif mode == "2":
        craft_replies_mode()
    else:
        print("Invalid choice. Exiting.")