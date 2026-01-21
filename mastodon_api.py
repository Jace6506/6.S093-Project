"""Mastodon API integration functions."""
import re
import config
from utils import truncate_post_to_limit


def search_mastodon_posts(keyword, limit=5):
    """Search for recent posts on Mastodon by keyword."""
    if not config.mastodon:
        print("⚠️  Mastodon credentials not configured.")
        return []
    
    try:
        # Search for posts containing the keyword
        # Note: search() doesn't accept limit parameter, so we slice results afterward
        search_results = config.mastodon.search(keyword, result_type='statuses')
        
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


def reply_to_post(post_id, reply_text):
    """Reply to a specific Mastodon post."""
    if not config.mastodon:
        return None
    
    try:
        status = config.mastodon.status_post(reply_text, in_reply_to_id=post_id)
        return status
    except Exception as e:
        print(f"❌ Error replying to post: {e}")
        return None


def post_to_mastodon(post_content, image_path=None):
    """Post content to Mastodon, optionally with an image."""
    import os
    
    if not config.mastodon:
        print("⚠️  Mastodon credentials not configured. Skipping post.")
        print("   Set MASTODON_INSTANCE_URL and MASTODON_ACCESS_TOKEN to enable posting.")
        return None
    
    # Final safety check - ensure post doesn't exceed 500 characters
    if len(post_content) > 500:
        print(f"⚠️  Post is {len(post_content)} characters, truncating to 500...")
        post_content = truncate_post_to_limit(post_content, max_length=500)
    
    try:
        # Verify credentials first
        account = config.mastodon.account_verify_credentials()
        print(f"   Authenticated as: @{account['username']}")
        
        # Post to Mastodon with or without media
        if image_path and os.path.exists(image_path):
            # Upload media first
            media = config.mastodon.media_post(image_path)
            # Post with media
            status = config.mastodon.status_post(post_content, media_ids=[media['id']])
        else:
            # Post without media
            status = config.mastodon.status_post(post_content)
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
            print(f"   4. Current instance URL: {config.MASTODON_INSTANCE_URL}")
        elif "401" in error_msg or "Unauthorized" in error_msg:
            print("\n💡 Your access token may be invalid or expired.")
            print("   Generate a new token in Settings → Development")
        elif "403" in error_msg or "Forbidden" in error_msg:
            print("\n💡 Your access token may not have the required permissions.")
            print("   Make sure 'write:statuses' scope is enabled when creating the app")
        
        return None
